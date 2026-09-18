#!/usr/bin/env python3
"""Fusionne web/ en fichiers HTML autonomes.

  dist/atelier-nmt-apercu.html  page complète, à ouvrir dans un navigateur
  dist/artifact.html            même page sans enveloppe html/head/body,
                                avec des données d'exemple, pour publication

L'APK, lui, charge les fichiers séparés depuis ses assets : rien de tout ceci
n'entre dans l'application.
"""

import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', 'web')
DIST = os.path.join(HERE, '..', 'dist')


def read(rel, base=ROOT):
    with open(os.path.join(base, rel)) as f:
        return f.read()


def inline(html, extra_script=None):
    html = html.replace(
        '<link rel="stylesheet" href="css/app.css">',
        '<style>\n' + read('css/app.css') + '</style>'
    )
    html = re.sub(
        r'<script src="([^"]+)"></script>',
        lambda m: '<script>\n' + read(m.group(1)) + '</script>',
        html
    )
    if extra_script:
        html = html.replace('</body>', '<script>\n' + extra_script + '</script>\n</body>')
    return html


base = read('index.html')
os.makedirs(DIST, exist_ok=True)

# 1. page complète
full = inline(base)
with open(os.path.join(DIST, 'atelier-nmt-apercu.html'), 'w') as f:
    f.write(full)

# 2. version publiable : données d'exemple, et on retire l'enveloppe
#    html/head/body que la plateforme ajoute elle-même
demo = inline(base, extra_script=read('demo-seed.js', HERE))

head = re.search(r'<head>(.*?)</head>', demo, re.S).group(1)
body = re.search(r'<body>(.*?)</body>', demo, re.S).group(1)

keep = []
for m in re.finditer(r'(<title>.*?</title>|<style>.*?</style>)', head, re.S):
    keep.append(m.group(1))

# la plateforme applique déjà les marges de sécurité sur :root
art = '\n'.join(keep) + '\n' + body
art = art.replace('padding:calc(var(--safe-t) + 14px) 16px 12px',
                  'padding:14px 16px 12px')
art = art.replace('#topbar{\n  position:sticky;top:0;',
                  '#topbar{\n  position:sticky;top:env(safe-area-inset-top,0px);')

with open(os.path.join(DIST, 'artifact.html'), 'w') as f:
    f.write(art)

print('page complète :', round(len(full) / 1024, 1), 'Ko')
print('version publiable :', round(len(art) / 1024, 1), 'Ko')
