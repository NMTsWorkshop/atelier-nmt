// Juste assez de LVGL pour que le compilateur relise nmt_vue.h sur un PC.
//
// Ce n'est pas un faux LVGL qui marche : c'est un jeu de signatures copiees
// sur les en-tetes de LVGL 9.3.0. Ca n'execute rien, mais ca attrape les
// noms mal orthographies, les arguments en trop et les constantes qui ont
// change de nom entre deux versions — ce qui est exactement ce qui nous
// couterait un aller-retour de flashage.
#pragma once
#include <cstdint>

struct lv_obj_t;
struct lv_font_t;
struct lv_event_t;

typedef struct { uint8_t b, g, r; } lv_color_t;
typedef uint8_t lv_opa_t;
typedef int32_t lv_coord_t;
typedef void (*lv_event_cb_t)(lv_event_t*);

#define LV_OPA_COVER 255
#define LV_OPA_TRANSP 0

enum { LV_ALIGN_TOP_LEFT = 1, LV_ALIGN_TOP_RIGHT, LV_ALIGN_CENTER };
enum { LV_FLEX_FLOW_COLUMN = 1, LV_FLEX_FLOW_ROW };
enum { LV_DIR_VER = 1, LV_DIR_HOR };
enum { LV_SCROLLBAR_MODE_OFF = 0, LV_SCROLLBAR_MODE_AUTO };
enum {
    LV_OBJ_FLAG_SCROLLABLE = 1,
    LV_OBJ_FLAG_CLICKABLE = 2,
    LV_OBJ_FLAG_EVENT_BUBBLE = 4,
};
enum {
    LV_LABEL_LONG_MODE_WRAP = 0,
    LV_LABEL_LONG_MODE_DOTS,
    LV_LABEL_LONG_MODE_SCROLL,
    LV_LABEL_LONG_MODE_SCROLL_CIRCULAR,
    LV_LABEL_LONG_MODE_CLIP,
};
enum { LV_EVENT_CLICKED = 1 };

extern const lv_font_t lv_font_montserrat_14;
extern const lv_font_t lv_font_montserrat_20;
extern const lv_font_t lv_font_montserrat_28;

lv_color_t lv_color_hex(uint32_t c);
lv_obj_t* lv_screen_active(void);
lv_obj_t* lv_obj_create(lv_obj_t* parent);
lv_obj_t* lv_label_create(lv_obj_t* parent);
void lv_label_set_text(lv_obj_t* obj, const char* text);
void lv_label_set_long_mode(lv_obj_t* obj, int mode);
void lv_obj_set_size(lv_obj_t* obj, int32_t w, int32_t h);
void lv_obj_set_width(lv_obj_t* obj, int32_t w);
void lv_obj_set_pos(lv_obj_t* obj, int32_t x, int32_t y);
void lv_obj_align(lv_obj_t* obj, int align, int32_t x, int32_t y);
void lv_obj_clean(lv_obj_t* obj);
void lv_obj_add_flag(lv_obj_t* obj, int f);
void lv_obj_remove_flag(lv_obj_t* obj, int f);
void lv_obj_set_flex_flow(lv_obj_t* obj, int flow);
void lv_obj_set_scroll_dir(lv_obj_t* obj, int dir);
void lv_obj_set_scrollbar_mode(lv_obj_t* obj, int mode);
void lv_obj_add_event_cb(lv_obj_t* obj, lv_event_cb_t cb, int filter, void* ud);
void lv_obj_set_style_bg_color(lv_obj_t* obj, lv_color_t v, int sel);
void lv_obj_set_style_bg_opa(lv_obj_t* obj, lv_opa_t v, int sel);
void lv_obj_set_style_border_color(lv_obj_t* obj, lv_color_t v, int sel);
void lv_obj_set_style_border_width(lv_obj_t* obj, int32_t v, int sel);
void lv_obj_set_style_radius(lv_obj_t* obj, int32_t v, int sel);
void lv_obj_set_style_pad_all(lv_obj_t* obj, int32_t v, int sel);
void lv_obj_set_style_pad_row(lv_obj_t* obj, int32_t v, int sel);
void lv_obj_set_style_text_font(lv_obj_t* obj, const lv_font_t* v, int sel);
void lv_obj_set_style_text_color(lv_obj_t* obj, lv_color_t v, int sel);
void lv_timer_handler(void);
