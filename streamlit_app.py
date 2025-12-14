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

col_fecha   = pick(df.columns, ["fecha", "periodo", "período", "mes", "indice_tiempo", "time"])
col_region  = pick(df.columns, ["region", "región"])
col_div     = pick(df.columns, ["division", "división", "capitulo", "capítulo", "categoria", "categoría"])
col_valor   = pick(df.columns, ["indice", "índice", "nivel", "valor", "ipc", "variacion", "variación"])

if col_fecha  is None: col_fecha  = st.sidebar.selectbox("Columna de fecha/mes", df.columns)
if col_region is None: col_region = st.sidebar.selectbox("Columna de región", df.columns)
if col_div    is None: col_div    = st.sidebar.selectbox("Columna de división/categoría", df.columns)
if col_valor  is None: col_valor  = st.sidebar.selectbox("Columna de índice/valor", df.columns)

df[col_fecha] = pd.to_datetime(df[col_fecha], errors="coerce")
df = df.dropna(subset=[col_fecha])
df = df.sort_values([col_region, col_div, col_fecha])

if df[col_valor].median() > 50:
    df["var_mensual_%"]    = df.groupby([col_region, col_div])[col_valor].pct_change(1) * 100
    df["var_interanual_%"] = df.groupby([col_region, col_div])[col_valor].pct_change(12) * 100
else:
    df["var_mensual_%"] = df[col_valor] if "mensual" in col_valor.lower() else np.nan
    df["var_interanual_%"] = df[col_valor] if "interanual" in col_valor.lower() else np.nan

df["anio"] = df[col_fecha].dt.year
df["mes_label"] = df[col_fecha].dt.to_period("M").astype(str)

st.sidebar.header("3) Filtros")
anio_min, anio_max = int(df["anio"].min()), int(df["anio"].max())
rango_anios = st.sidebar.slider("Rango de años", anio_min, anio_max, (max(anio_min, 2016), anio_max))
regiones = sorted(df[col_region].dropna().unique().tolist())
region_sel = st.sidebar.multiselect("Región (para comparar)", regiones, default=regiones[:1])
meses = sorted(df["mes_label"].unique().tolist())
mes_ref = st.sidebar.selectbox("Mes de referencia (para barras/heatmap)", meses, index=len(meses)-1)

tab1, tab2, tab3, tab4 = st.tabs(["Exploración (línea)", "Divisiones (barras)", "Mapa de calor", "Series temporales (suavizado)"])

with tab1:
    st.subheader("Evolución interanual del IPC (%)")
    df_line = df[(df["anio"] >= rango_anios[0]) & (df["anio"] <= rango_anios[1])].copy()
    mask_general = df_line[col_div].str.lower().str.contains("nivel general|nivel gral|general", regex=True, na=False)
    if mask_general.any():
        df_general = df_line[mask_general].copy()
    else:
        df_general = (df_line.groupby([col_fecha, col_region], as_index=False)["var_interanual_%"].mean()
                      .assign(**{col_div: "Nivel general (promedio divisiones)"}))
    if region_sel:
        df_general = df_general[df_general[col_region].isin(region_sel)]
    chart_line = (alt.Chart(df_general)
                    .mark_line()
                    .encode(
                        x=alt.X(f"{col_fecha}:T", title="Fecha"),
                        y=alt.Y("var_interanual_%:Q", title="Interanual (%)"),
                        color=alt.Color(f"{col_region}:N", title="Región"),
                        tooltip=[col_fecha, col_region, "var_interanual_%"]
                    ).properties(height=350))
    st.altair_chart(chart_line, use_container_width=True)

with tab2:
    st.subheader(f"Variación interanual por división — {mes_ref}")
    df_mes = df[df["mes_label"] == mes_ref].copy()
    if region_sel:
        df_mes = df_mes[df_mes[col_region].isin(region_sel)]
    chart_bar = (alt.Chart(df_mes)
                   .mark_bar()
                   .encode(
                       x=alt.X("var_interanual_%:Q", title="Interanual (%)"),
                       y=alt.Y(f"{col_div}:N", sort='-x', title="División"),
                       color=alt.Color(f"{col_region}:N", title="Región"),
                       tooltip=[col_region, col_div, "var_interanual_%"]
                   ).properties(height=520))
    st.altair_chart(chart_bar, use_container_width=True)

with tab3:
    st.subheader(f"Mapa de calor — {mes_ref} (interanual %)")
    df_heat = df[df["mes_label"] == mes_ref].copy()
    heat = (alt.Chart(df_heat)
              .mark_rect()
              .encode(
                  x=alt.X(f"{col_div}:N", title="División"),
                  y=alt.Y(f"{col_region}:N", title="Región"),
                  color=alt.Color("var_interanual_%:Q", title="Interanual (%)"),
                  tooltip=[col_region, col_div, "var_interanual_%"]
              ).properties(height=360))
    st.altair_chart(heat, use_container_width=True)

with tab4:
    st.subheader("Series temporales: media móvil y suavizado exponencial")
    st.write("Esta sección aplica técnicas simples de series temporales para observar tendencia y reducir ruido.")

    # Tomamos la misma serie 'general' usada en tab1 (por región y fecha)
    df_ts = df_general.copy()

    # Seguridad: ordenar por fecha
    df_ts = df_ts.sort_values([col_region, col_fecha])

    # Controles simples (en el panel lateral o acá; lo dejamos acá para no cargar la sidebar)
    ventana = st.selectbox("Ventana de media móvil (meses)", [3, 6, 12], index=1)
    alpha = st.slider("Alpha (suavizado exponencial)", 0.05, 0.95, 0.30, 0.05)

    # Calculamos suavizados por región (cada región su propia serie)
    df_ts["media_movil"] = df_ts.groupby(col_region)["var_interanual_%"].transform(
        lambda s: s.rolling(window=ventana, min_periods=1).mean()
    )
    df_ts["suav_exp"] = df_ts.groupby(col_region)["var_interanual_%"].transform(
        lambda s: s.ewm(alpha=alpha, adjust=False).mean()
    )

    # Pasamos a formato largo para graficar 3 líneas en 1 chart
    df_plot = df_ts[[col_fecha, col_region, "var_interanual_%", "media_movil", "suav_exp"]].copy()
    df_plot = df_plot.rename(columns={
        "var_interanual_%": "Original",
        "media_movil": f"Media móvil ({ventana})",
        "suav_exp": f"Suavizado exp (α={alpha:.2f})"
    })

    df_long = df_plot.melt(id_vars=[col_fecha, col_region], var_name="Serie", value_name="Valor")

    chart_ts = (
    alt.Chart(df_long)
    .mark_line()
    .encode(
        x=alt.X(f"{col_fecha}:T", title="Fecha"),
        y=alt.Y("Valor:Q", title="Inflación interanual (%)"),
        color=alt.Color("Serie:N", title="Serie"),
        tooltip=[col_fecha, col_region, "Serie", "Valor"]
    )
    .facet(
        row=alt.Row(f"{col_region}:N", title="Región")
    )
    .properties(height=160)
)

    st.altair_chart(chart_ts, use_container_width=True)

    st.markdown("**Interpretación rápida:** la media móvil suaviza picos y muestra tendencia; el suavizado exponencial responde más rápido a cambios recientes.")


