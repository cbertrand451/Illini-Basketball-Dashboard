import streamlit as st
from pathlib import Path
import json

def colored_metric(label=None, 
                   value=None,
                   lab_color="#000000", 
                   val_color= "#000000", 
                   delta=None, 
                   delta_b_color="#FFFFFF", 
                   delta_t_color="#000000",
                   align="left", 
                   bg_color=None,
                   border_color=None):
    align_map = {
        "left": ("flex-start", "left"),
        "center": ("center", "center"),
        "right": ("flex-end", "right"),
        }
    flex_align, text_align = align_map.get(align, ("flex-start", "left"))
    delta_html = ""
    if delta:
        delta_html = f"""<div class="wm-metric-delta" style="
            display: flex;
            justify-content: {flex_align};
            margin-top: 4px;
        ">
            <div style="
                display: inline-block;
                background-color: {delta_b_color};
                color: {delta_t_color};
                padding: 4px 8px;
                border-radius: 20px;
                font-family: 'Source Sans Pro', sans-serif;
                font-size: 14px;
                font-weight: 600;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            ">
                {delta}
            </div>
        </div>
        """

    # conditional card styling
    card_styles = ""
    if bg_color:
        card_styles = f"""
            background-color: {bg_color if bg_color else "transparent"};
            border-radius: 14px;
            padding: 16px 18px;
            margin-bottom: 12px;
        """

    html = f"""
    <div class="wm-metric-card" style="{card_styles}">
        <div style="
            margin-bottom: 12px;
            text-align: {text_align};
        ">
            <div style="
                font-family: 'Source Sans Pro', sans-serif;
                font-size: 14px; 
                color: {lab_color}; 
                line-height: normal;
                margin: 0;
                padding: 0;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                height: auto;
                min-height: 1.5rem;
                display: flex;
                justify-content: {flex_align};
                align-items: center;
                font-weight: 500;
            ">
                {label}
            </div>
            <div style="
                font-size: 36px; 
                font-weight: 500; 
                color: {val_color};
                line-height: normal;
                padding-bottom: 0.25rem;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                justify-content: {flex_align};
                width: 100%;">
                {value}
            </div>
        {delta_html}
    """
    return html


def divider(color="#000000"):
    st.markdown(
        f"<hr style='border: 1px solid {color};'>",
        unsafe_allow_html=True
)


def tab_styler(primary: str, secondary: str, sectext: str):
    st.markdown(
        f"""
        <style>
        div[data-testid="stTabs"] {{
            margin-top: 1.25rem;
        }}

        div[data-testid="stTabs"] div[role="tablist"] {{
            display: flex;
            justify-content: center;
            gap: 32px;
            margin: 0 auto;
            border-bottom: none !important;
            box-shadow: none !important;
            overflow: visible !important;
        }}

        div[data-testid="stTabs"] button[role="tab"],
        button[data-baseweb="tab"] {{
            background-color: transparent !important;
            color: {primary} !important;
            font-weight: 700 !important;
            font-size: 1.5rem !important;
            padding: 12px 26px !important;
            border-radius: 999px !important;
            border: 3px solid {primary} !important;
            transition: all 0.15s ease;
        }}

        div[data-testid="stTabs"] button[role="tab"]:hover,
        button[data-baseweb="tab"]:hover {{
            background-color: {secondary} !important;
            color: {sectext} !important;
        }}

        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"],
        button[data-baseweb="tab"][aria-selected="true"] {{
            background-color: {primary} !important;
            color: white !important;
            transform: scale(1.25);
        }}

        div[data-testid="stTabs"] div[data-baseweb="tab-border"],
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"],
        div[data-testid="stTabs"] hr {{
            display: none !important;
        }}

        div[data-testid="stTabs"] div[role="tablist"]::after {{
            display: none !important;
            content: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    

def pill_button_styler(
    primary: str,
    secondary: str,
    font_size: str = "2rem",
    padding_y: str = "10px",
    border_width: str = "3px",
    scale_active: float = 1.05,
):
    st.markdown(
        f"""
        <style>
        /* base pill button */
        div.stButton > button {{
            background-color: transparent !important;
            color: {primary} !important;
            font-weight: 700 !important;
            font-size: {font_size} !important;
            padding: {padding_y} 0 !important;
            border-radius: 999px !important;
            border: {border_width} solid {primary} !important;
            transition: all 0.15s ease;
            width: 100%;
        }}

        /* hover */
        div.stButton > button:hover {{
            background-color: {secondary} !important;
            color: white !important;
        }}

        /* focus (keyboard nav) */
        div.stButton > button:focus {{
            outline: none !important;
            box-shadow: none !important;
        }}

        /* pressed / active click */
        div.stButton > button:active {{
            transform: scale({scale_active});
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_theme_colors(theme_path=None, target_globals=None):
    if theme_path is None:
        theme_path = Path(__file__).resolve().parent.parent / 'colors' / 'theme.json'
    else:
        theme_path = Path(theme_path)
    colors = json.loads(theme_path.read_text(encoding='utf-8'))
    if target_globals is None:
        target_globals = globals()
    for name, value in colors.items():
        target_globals[name] = value
    return colors


THEME_COLORS = load_theme_colors()
