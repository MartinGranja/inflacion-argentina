import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

st.set_page_config(page_title="Inflación en Argentina — INDEC", layout="wide")
st.title("Inflación en Argentina — INDEC (2016–actual)")
st.sidebar.header("1) Cargar CSV del IPC (INDEC)")
modo = st.sidebar.radio("¿Cómo cargar?", ["Subir CSV", "Pegar URL CSV"])

def cargar_csv(label):
    if modo == "Subir CSV":
        f = st.sidebar.file_uploader(label, type=["csv"])
        if f:
            return pd.read_csv(f)
    else:
        url = st.sidebar.text_input(label, "")
        if url:
            return pd.read_csv(url)
    return None

df_ipc = cargar_csv("Archivo/URL del CSV de IPC (mensual, por divisiones y regiones)")

if df_ipc is None:
    st.info("📄 Cargá el CSV de IPC para comenzar (desde la barra lateral).")
    st.stop()

df = df_ipc.copy()

st.sidebar.header("2) Elegir columnas")

def pick(colnames, patrones):
    for p in patrones:
        for c in colnames:
            if p in c.lower():
                return c
    return None

col_fecha = pick(df.columns, ["fecha", "periodo", "período", "mes", "indice_tiempo", "time"])
col_region = pick(df.columns, ["region", "región"])
col_div = pick(df.columns, ["division", "división", "capitulo", "capítulo", "categoria", "categoría"])
col_valor = pick(df.columns, ["indice", "índice", "nivel", "valor", "ipc", "variacion", "variación"])

if col_fecha is None: col_fecha = st.sidebar.selectbox("Columna de fecha/mes", df.columns)
if col_region is None: col_region = st.sidebar.selectbox("Columna de región", df.columns)
if col_div is None: col_div = st.sidebar.selectbox("Columna de división/categoría", df.columns)
if col_valor is None: col_valor = st.sidebar.selectbox("Columna de índice/valor", df.columns)

df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
df = df.dropna(subset=[col_fecha])
df = df.sort_values([col_region, col_div, col_fecha])

if df[col_valor].median() > 50:
    df["var_mensual_%"] = df.groupby([col_region, col_div])[col_valor].pct_change(1) * 100
    df["var_interanual_%"] = df.groupby([col_region, col_div])[col_valor].pct_change(12) * 100
else:
    df["var_mensual_%"] = df[col_valor]
    df["var_interanual_%"] = df[col_valor]

df["anio"] = df[col_fecha].dt.year
df["mes_label"] = df[col_fecha].dt.to_period("M").astype(str)

st.sidebar.header("3) Filtros")
anio_min, anio_max = int(df["anio"].min()), int(df["anio"].max())
rango_anios = st.sidebar.slider("Rango de años", anio_min, anio_max, (max(anio_min, 2016), anio_max))
regiones = sorted(df[col_region].dropna().unique().tolist())
region_sel = st.sidebar.selectbox("Región", regiones)
meses = sorted(df["mes_label"].unique().tolist())
mes_ref = st.sidebar.selectbox("Mes de referencia", meses, index=len(meses)-1)

df = df[(df["anio"] >= rango_anios[0]) & (df["anio"] <= rango_anios[1])]
df = df[df[col_region] == region_sel]

tab1, tab2, tab3, tab4 = st.tabs([
    "Exploración (línea)",
    "Divisiones (barras)",
    "Mapa de calor",
    "Series temporales (suavizado)"
])

with tab1:
    mask_general = df[col_div].str.lower().str.contains("nivel general|general", na=False)
    if mask_general.any():
        df_general = df[mask_general]
    else:
        df_general = df.groupby(col_fecha, as_index=False)["var_interanual_%"].mean()
    chart = alt.Chart(df_general).mark_line().encode(
        x=alt.X(f"{col_fecha}:T", title="Fecha"),
        y=alt.Y("var_interanual_%:Q", title="Interanual (%)"),
        tooltip=[col_fecha, "var_interanual_%"]
    ).properties(height=350)
    st.altair_chart(chart, use_container_width=True)

with tab2:
    df_mes = df[df["mes_label"] == mes_ref]
    chart = alt.Chart(df_mes).mark_bar().encode(
        x=alt.X("var_interanual_%:Q", title="Interanual (%)"),
        y=alt.Y(f"{col_div}:N", sort="-x", title="División"),
        tooltip=[col_div, "var_interanual_%"]
    ).properties(height=500)
    st.altair_chart(chart, use_container_width=True)

with tab3:
    df_mes = df[df["mes_label"] == mes_ref]
    chart = alt.Chart(df_mes).mark_rect().encode(
        x=alt.X(f"{col_div}:N", title="División"),
        y=alt.Y(f"{col_region}:N", title="Región"),
        color=alt.Color("var_interanual_%:Q", title="Interanual (%)"),
        tooltip=[col_div, col_region, "var_interanual_%"]
    ).properties(height=350)
    st.altair_chart(chart, use_container_width=True)

with tab4:
    st.subheader("Series temporales: media móvil y suavizado exponencial")
    ventana = st.selectbox("Ventana de media móvil (meses)", [3, 6, 12], index=1)
    alpha = st.slider("Alpha (suavizado exponencial)", 0.05, 0.95, 0.3, 0.05)

    ts = df_general.sort_values(col_fecha).copy()
    ts["Media móvil"] = ts["var_interanual_%"].rolling(ventana, min_periods=1).mean()
    ts["Suavizado exponencial"] = ts["var_interanual_%"].ewm(alpha=alpha, adjust=False).mean()

    ts_long = ts.melt(
        id_vars=[col_fecha],
        value_vars=["var_interanual_%", "Media móvil", "Suavizado exponencial"],
        var_name="Serie",
        value_name="Valor"
    )

    chart = alt.Chart(ts_long).mark_line().encode(
        x=alt.X(f"{col_fecha}:T", title="Fecha"),
        y=alt.Y("Valor:Q", title="Inflación interanual (%)"),
        color=alt.Color("Serie:N", title="Serie"),
        tooltip=[col_fecha, "Serie", "Valor"]
    ).properties(height=350)

    st.altair_chart(chart, use_container_width=True)



