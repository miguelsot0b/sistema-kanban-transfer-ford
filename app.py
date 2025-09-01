import streamlit as st
import pandas as pd
import math
import os

# Configuración de la página
st.set_page_config(
    page_title="Sistema Kanban Transfer Ford",
    page_icon="🏭",
    layout="wide"
)

# Título principal
st.title("🏭 Sistema Kanban Transfer Ford")

# Función para cargar el catálogo
@st.cache_data
def cargar_catalogo():
    return pd.read_csv("catalogo.csv")

# Cargar catálogo
catalogo = cargar_catalogo()

# Obtener lista de máquinas únicas
maquinas = sorted(catalogo['Maquina'].unique())

# Barra lateral para entrada de inventario actual
st.sidebar.header("📦 Inventario Actual")

# Inicializar la sesión para inventario si no existe
if 'inventario' not in st.session_state:
    st.session_state.inventario = {parte: 0 for parte in catalogo['Parte'].unique()}
    st.session_state.temp_inventario = {parte: 0 for parte in catalogo['Parte'].unique()}

# Formulario para actualizar inventario
with st.sidebar.form("form_inventario"):
    st.subheader("Ingrese el inventario actual:")
    
    # Crear input para cada número de parte único
    partes_unicas = sorted(catalogo['Parte'].unique())
    
    for parte in partes_unicas:
        # Usar valores temporales para no actualizar inmediatamente
        st.session_state.temp_inventario[parte] = st.number_input(
            f"{parte}", 
            min_value=0, 
            value=st.session_state.inventario[parte],
            key=f"inv_{parte}"
        )
    
    # Botón para actualizar
    submitted = st.form_submit_button("Actualizar Inventario")
    
    # Solo actualizar el inventario real cuando se presiona el botón
    if submitted:
        st.session_state.inventario = st.session_state.temp_inventario.copy()
        st.success("✅ Inventario actualizado correctamente")

# Calcular métricas
def calcular_metricas(catalogo, inventario):
    # Crear una copia del catálogo para no modificar el original
    df = catalogo.copy()
    
    # Agregar columna de inventario actual
    df['Inventario'] = df['Parte'].map(inventario)
    
    # Calcular faltante
    df['Faltante'] = df['Objetivo'] - df['Inventario']
    df['Faltante'] = df['Faltante'].apply(lambda x: max(0, x))  # No permitir faltantes negativos
    
    # Calcular cajas necesarias
    df['CajasNecesarias'] = df['Faltante'] / df['StdPack']
    df['CajasNecesarias'] = df['CajasNecesarias'].apply(lambda x: math.ceil(x) if x > 0 else 0)
    
    # Calcular tiempo necesario (horas)
    df['TiempoNecesario'] = df['Faltante'] / df['Rate']
    
    # Crear un ranking temporal para asignar prioridades
    df_temp = df.copy()
    df_temp = df_temp[df_temp['Faltante'] > 0]  # Solo considerar partes con faltante
    
    if not df_temp.empty:
        # Asignar prioridad basada en tiempo necesario (más tiempo → mayor prioridad)
        df_temp = df_temp.sort_values('TiempoNecesario', ascending=False)
        df_temp['Prioridad'] = range(1, len(df_temp) + 1)
        
        # Fusionar de vuelta las prioridades al DataFrame original
        df = df.merge(df_temp[['Parte', 'Maquina', 'Prioridad']], 
                     on=['Parte', 'Maquina'], 
                     how='left')
    else:
        df['Prioridad'] = None
    
    return df

# Calcular métricas basadas en inventario actual
df_metricas = calcular_metricas(catalogo, st.session_state.inventario)

# Sección principal - Dashboard por máquina
st.header("📊 Dashboard por Máquina")

# Crear una fila para cada máquina
for maquina in maquinas:
    st.subheader(f"Máquina: {maquina}")
    
    # Filtrar partes para esta máquina
    df_maquina = df_metricas[df_metricas['Maquina'] == maquina].copy()
    
    # Si hay partes con faltante para esta máquina
    df_faltante = df_maquina[df_maquina['Faltante'] > 0].sort_values('Prioridad')
    
    if not df_faltante.empty:
        # Tomar la parte con mayor prioridad (número más bajo)
        parte_asignada = df_faltante.iloc[0]
        
        # Crear columnas para mostrar la información
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        with col1:
            st.metric("Producto", parte_asignada['Parte'])
        
        with col2:
            st.metric("Inventario", f"{int(parte_asignada['Inventario'])}")
            
        with col3:
            st.metric("Objetivo", f"{int(parte_asignada['Objetivo'])}")
            
        with col4:
            st.metric("Cajas a Correr", f"{int(parte_asignada['CajasNecesarias'])}")
            
        with col5:
            st.metric("Tiempo (horas)", f"{parte_asignada['TiempoNecesario']:.2f}")
            
        with col6:
            st.metric("Prioridad", f"{int(parte_asignada['Prioridad'])}")
    else:
        st.info("🟢 Máquina Libre")
    
    st.divider()  # Separador visual entre máquinas

# Tabla completa con todos los cálculos
st.header("📋 Tabla General de Producción")

# Preparar la tabla para mostrar
df_tabla = df_metricas.copy()
df_tabla = df_tabla.sort_values(['Maquina', 'Prioridad'], na_position='last')
df_tabla = df_tabla.fillna({'Prioridad': '-'})

# Formatear columnas numéricas
df_tabla['Inventario'] = df_tabla['Inventario'].astype(int)
df_tabla['Objetivo'] = df_tabla['Objetivo'].astype(int)
df_tabla['Faltante'] = df_tabla['Faltante'].astype(int)
df_tabla['CajasNecesarias'] = df_tabla['CajasNecesarias'].astype(int)
df_tabla['TiempoNecesario'] = df_tabla['TiempoNecesario'].round(2)

# Columnas a mostrar
columnas_mostrar = [
    'Parte', 'Maquina', 'Inventario', 'Objetivo', 
    'Faltante', 'StdPack', 'CajasNecesarias', 
    'Rate', 'TiempoNecesario', 'Prioridad'
]

# Mostrar la tabla
st.dataframe(
    df_tabla[columnas_mostrar], 
    use_container_width=True,
    hide_index=True
)

# Información sobre el último cálculo
st.caption("La prioridad se calcula según el tiempo necesario para alcanzar el objetivo.")
