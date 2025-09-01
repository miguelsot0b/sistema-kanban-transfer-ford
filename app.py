import streamlit as st
import pandas as pd
import math
import os
import hashlib

try:
    # Configuración de la página
    st.set_page_config(
        page_title="Sistema Kanban Transfer Ford",
        page_icon="🏭",
        layout="wide"
    )
except Exception as e:
    st.write(f"Error en configuración: {e}")

# Inicializar estados de sesión
if 'page' not in st.session_state:
    st.session_state.page = 'dashboard'

if 'is_admin' not in st.session_state:
    st.session_state.is_admin = False

# Función para cambiar de página
def change_page(page):
    st.session_state.page = page

# Función para autenticación de admin
def login_admin(username, password):
    # Hash simple para demostración (en producción usar un método más seguro)
    hashed_pw = hashlib.sha256(password.encode()).hexdigest()
    # Usuario admin con contraseña "admin123"
    if username == "admin" and hashed_pw == "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9":
        st.session_state.is_admin = True
        return True
    return False

# Título principal
st.title("🏭 Sistema Kanban Transfer Ford")

# Datos de ejemplo en caso de que falle la carga del CSV
DATOS_EJEMPLO = [
    ["CX430 Header Front LH", 40, 978, "Transfer 7", 120],
    ["CX430 Header Front RH", 40, 978, "Transfer 7", 120],
    ["CX430 Header Rear LH", 56, 880, "Transfer 7", 110],
    ["CX430 Header Rear RH", 56, 880, "Transfer 7", 110],
    ["CX430 OB RR LH", 70, 978, "Transfer 8", 130],
    ["CX430 OB RR RH", 70, 978, "Transfer 8", 130]
]

# Función para cargar el catálogo
# Usar el decorador de cache adecuado según la versión
if hasattr(st, 'cache_data'):
    cache_decorator = st.cache_data
else:
    cache_decorator = st.cache

@cache_decorator
def cargar_catalogo():
    try:
        # Intentar cargar desde la ruta relativa
        return pd.read_csv("catalogo.csv")
    except Exception as e:
        st.warning(f"No se pudo cargar el archivo catalogo.csv: {e}")
        st.info("Usando datos de ejemplo predeterminados")
        # Usar datos de ejemplo
        return pd.DataFrame(
            DATOS_EJEMPLO,
            columns=["Parte", "StdPack", "Objetivo", "Maquina", "Rate"]
        )

# Cargar catálogo
catalogo = cargar_catalogo()

# Obtener lista de máquinas únicas
maquinas = sorted(catalogo['Maquina'].unique())

# Inicializar la sesión para inventario si no existe
if 'inventario' not in st.session_state:
    st.session_state.inventario = {parte: 0 for parte in catalogo['Parte'].unique()}

if 'temp_inventario' not in st.session_state:
    st.session_state.temp_inventario = {parte: 0 for parte in catalogo['Parte'].unique()}

# Barra lateral con navegación
st.sidebar.header("Navegación")

# Botón para ir a la página de actualización de inventario
if st.sidebar.button("📝 Actualizar Inventario"):
    change_page('update_inventory')
    
# Botón para ir al dashboard principal
if st.sidebar.button("📊 Dashboard"):
    change_page('dashboard')

# Sección para administradores
st.sidebar.header("Administración")

# Formulario de login para administradores
with st.sidebar.expander("Acceso Administrador"):
    admin_user = st.text_input("Usuario", key="admin_user")
    admin_pwd = st.text_input("Contraseña", type="password", key="admin_pwd")
    
    if st.button("Iniciar Sesión"):
        if login_admin(admin_user, admin_pwd):
            st.success("✅ Acceso concedido")
            change_page('admin')
        else:
            st.error("❌ Usuario o contraseña incorrectos")

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

# Contenido principal basado en la página seleccionada
if st.session_state.page == 'dashboard':
    # PÁGINA PRINCIPAL - DASHBOARD
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
            col1, col2, col3, col4 = st.columns(4)
            
            # Mostrar el nombre completo del producto (sin truncar)
            with col1:
                st.write("**Producto:**")
                st.write(f"**{parte_asignada['Parte']}**")
                
            with col2:
                st.metric("Objetivo", f"{int(parte_asignada['Objetivo'])}")
                
            with col3:
                st.metric("Cajas a Correr", f"{int(parte_asignada['CajasNecesarias'])}")
                
            with col4:
                st.metric("Tiempo (horas)", f"{parte_asignada['TiempoNecesario']:.2f}")
            
            # Mostrar prioridad con un indicador visual
            st.write(f"**Prioridad:** {int(parte_asignada['Prioridad'])}")
            
            # Barra de progreso para visualizar el avance hacia el objetivo
            progreso = min(100, (parte_asignada['Inventario'] / parte_asignada['Objetivo']) * 100)
            st.progress(progreso / 100)
        else:
            st.info("🟢 Máquina Libre")
        
        st.divider()  # Separador visual entre máquinas

elif st.session_state.page == 'update_inventory':
    # PÁGINA DE ACTUALIZACIÓN DE INVENTARIO
    st.header("📝 Actualización de Inventario")
    
    with st.form("update_inventory_form"):
        st.write("Ingrese el inventario actual para cada producto:")
        
        # Crear dos columnas para organizar mejor los inputs
        col1, col2 = st.columns(2)
        
        # Crear input para cada número de parte único
        partes_unicas = sorted(catalogo['Parte'].unique())
        mitad = len(partes_unicas) // 2
        
        # Primera columna
        with col1:
            for i, parte in enumerate(partes_unicas[:mitad]):
                st.session_state.temp_inventario[parte] = st.number_input(
                    f"{parte}", 
                    min_value=0, 
                    value=st.session_state.inventario[parte],
                    key=f"inv_{parte}"
                )
        
        # Segunda columna
        with col2:
            for i, parte in enumerate(partes_unicas[mitad:]):
                st.session_state.temp_inventario[parte] = st.number_input(
                    f"{parte}", 
                    min_value=0, 
                    value=st.session_state.inventario[parte],
                    key=f"inv2_{parte}"
                )
        
        # Botón para guardar cambios
        submitted = st.form_submit_button("Guardar Cambios")
        
        if submitted:
            st.session_state.inventario = st.session_state.temp_inventario.copy()
            st.success("✅ Inventario actualizado correctamente")
            # Volver automáticamente al dashboard después de actualizar
            st.session_state.page = 'dashboard'
            st.rerun()
    
    # Botón para cancelar y volver al dashboard
    if st.button("Cancelar"):
        st.session_state.page = 'dashboard'
        st.rerun()

elif st.session_state.page == 'admin' and st.session_state.is_admin:
    # PÁGINA DE ADMINISTRADOR
    st.header("🔐 Panel de Administrador")
    
    # Tabla completa con todos los cálculos
    st.subheader("📋 Tabla General de Producción")
    
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
    
    # Opción para cerrar sesión de administrador
    if st.button("Cerrar Sesión"):
        st.session_state.is_admin = False
        st.session_state.page = 'dashboard'
        st.rerun()
else:
    # Redirigir a dashboard si hay algún error
    st.session_state.page = 'dashboard'
    st.rerun()
