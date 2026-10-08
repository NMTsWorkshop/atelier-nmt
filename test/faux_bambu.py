"""Un faux Bambu qui parle FTP en clair, pour vérifier ce que le relais
fait de la carte quand on coupe un envoi."""
import socket, threading, os


class FauxBambu:
    def __init__(self, dele_refuse=False, lenteur=0.0, seuil=0,
                 muet_apres_stor=False, coupe_apres=0):
        self.carte = {}
        self.supprimes = set()
        self.dele_refuse = dele_refuse
        self.lenteur = lenteur
        # au-delà de « seuil » octets reçus, le serveur attend qu'on le
        # relâche : c'est ce qui rend l'arrêt en vol reproductible au lieu
        # de dépendre de la vitesse de la machine qui fait tourner le test
        self.seuil = seuil
        # ne repond jamais le 226 : ce que fait une Bambu qui met trop
        # longtemps a ecrire sur sa carte
        self.muet_apres_stor = muet_apres_stor
        # ferme la connexion de donnees en plein milieu : une vraie
        # coupure, pas un silence apres coup
        self.coupe_apres = coupe_apres
        self.atteint = threading.Event()
        self.reprendre = threading.Event()
        self.journal = []
        self.srv = socket.socket()
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._boucle, daemon=True).start()

    def _boucle(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._session, args=(c,), daemon=True).start()

    def _session(self, c):
        f = c.makefile("rwb")
        f.write(b"220 faux bambu\r\n"); f.flush()
        pasv = None
        nom = None
        try:
            while True:
                ligne = f.readline()
                if not ligne:
                    return
                cmd = ligne.decode("utf-8", "replace").strip()
                self.journal.append(cmd.split()[0].upper() if cmd else "")
                haut = cmd.upper()
                if haut.startswith("USER") or haut.startswith("PASS"):
                    f.write(b"230 ok\r\n")
                elif haut.startswith("TYPE") or haut.startswith("PBSZ") or haut.startswith("PROT"):
                    f.write(b"200 ok\r\n")
                elif haut.startswith("PASV"):
                    pasv = socket.socket()
                    pasv.bind(("127.0.0.1", 0)); pasv.listen(1)
                    p = pasv.getsockname()[1]
                    f.write(("227 (127,0,0,1,%d,%d)\r\n" % (p >> 8, p & 255)).encode())
                elif haut.startswith("STOR"):
                    nom = cmd.split(None, 1)[1]
                    f.write(b"150 go\r\n"); f.flush()
                    d, _ = pasv.accept()
                    recu = 0
                    self.carte[nom] = 0
                    while True:
                        b = d.recv(1 << 16)
                        if not b:
                            break
                        recu += len(b)
                        # une fois le fichier supprimé, le STOR interrompu ne
                        # doit pas le faire réapparaître : un vrai serveur
                        # écrit dans un descripteur déjà détaché
                        if nom not in self.supprimes:
                            self.carte[nom] = recu
                        if self.coupe_apres and recu >= self.coupe_apres:
                            d.close()
                            break
                        if self.seuil and recu >= self.seuil:
                            self.atteint.set()
                            self.reprendre.wait(timeout=30)
                        if self.lenteur:
                            import time as _t
                            _t.sleep(self.lenteur)
                    d.close(); pasv.close(); pasv = None
                    # le DELE du relais peut tomber pendant qu'on lit encore :
                    # on relit le verdict à la fin, sinon la dernière écriture
                    # ferait réapparaître un fichier déjà supprimé
                    if nom in self.supprimes:
                        self.carte.pop(nom, None)
                    else:
                        self.carte[nom] = recu
                    if self.muet_apres_stor:
                        import time as _t
                        _t.sleep(30)        # le client abandonnera avant
                    f.write(b"226 Transfer complete\r\n")
                elif haut.startswith("DELE"):
                    cible = cmd.split(None, 1)[1]
                    if self.dele_refuse:
                        f.write(b"550 fichier verrouille\r\n")
                    else:
                        self.carte.pop(cible, None)
                        self.supprimes.add(cible)
                        f.write(b"250 DELE ok\r\n")
                elif haut.startswith("QUIT"):
                    f.write(b"221 bye\r\n"); f.flush()
                    return
                else:
                    f.write(b"200 ok\r\n")
                f.flush()
        except Exception:
            return
        finally:
            try:
                c.close()
            except Exception:
                pass
