import pandas as pd
from pathlib import Path
import streamlit as st


def history_csvs(path):
    df_raw = pd.read_csv(path)
    year_string = df_raw.iloc[0, 0]
    if pd.isna(year_string):
        return pd.DataFrame({"Year": []})
    tokens = [t.strip() for t in str(year_string).split(",")]
    years = [int(t) for t in tokens if t.isdigit()]
    df_years = pd.DataFrame({"Year": years})
    return df_years

# load css injections
def load_css(*paths):
    for path in paths:
        css = Path(path)
        if css.exists():
            st.markdown(
                f"<style>{css.read_text()}</style>",
                unsafe_allow_html=True
            )

import base64
from pathlib import Path
from urllib.request import urlopen

def image_to_data_uri(path_or_url, mime="image/webp"):
    if str(path_or_url).startswith(("http://", "https://")):
        with urlopen(path_or_url) as response:
            data = response.read()
            mime = response.info().get_content_type() or mime
    else:
        data = Path(path_or_url).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


