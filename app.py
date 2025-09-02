import streamlit as st
import pandas as pd
import numpy as np
import math
import os
import hashlib
import json
import datetime
from functools import lru_cache
import plotly.express as px
import plotly.graph_objects as go

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
    
if 'forzar_sincronizacion' not in st.session_state:
    st.session_state.forzar_sincronizacion = False

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

# Función para calcular hash de un archivo
@lru_cache(maxsize=8)
def calcular_hash_archivo(ruta_archivo):
    if not os.path.exists(ruta_archivo):
        return None
    
    try:
        with open(ruta_archivo, "rb") as f:
            contenido = f.read()
            return hashlib.md5(contenido).hexdigest()
    except Exception:
        return None

@cache_decorator(ttl=300)  # Caché de 5 minutos para reducir lecturas frecuentes
def cargar_catalogo():
    try:
        # Intentar cargar desde la ruta relativa
        df = pd.read_csv("catalogo.csv", dtype={
            'Parte': str,
            'StdPack': int,
            'Objetivo': int,
            'Maquina': str,
            'Rate': int
        })
        
        # Eliminar duplicados si los hay (más óptimo)
        df = df.drop_duplicates(subset=['Parte', 'Maquina'], keep='first')
        
        # Calcular hash del catálogo para detectar cambios
        hash_actual = calcular_hash_archivo("catalogo.csv")
        
        # Verificar si el hash ha cambiado
        if 'ultimo_hash_catalogo' in st.session_state and st.session_state.ultimo_hash_catalogo != hash_actual:
            # Si hay cambio en el catálogo, forzar sincronización de inventario
            st.session_state.forzar_sincronizacion = True
        
        # Actualizar hash en session_state
        st.session_state.ultimo_hash_catalogo = hash_actual
        
        return df
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

# Variables para control de cambios en el catálogo
if 'ultimo_hash_catalogo' not in st.session_state:
    st.session_state.ultimo_hash_catalogo = None

# Obtener lista de máquinas únicas
maquinas = sorted(catalogo['Maquina'].unique())

# Funciones para guardar y cargar inventario de forma persistente
def guardar_inventario(inventario, usuario="Sistema", cambios=None):
    try:
        # Convertir el inventario a un formato serializable más eficientemente
        inventario_serializable = {parte: int(cantidad) for parte, cantidad in inventario.items()}
        
        # Añadir metadatos
        datos = {
            "inventario": inventario_serializable,
            "ultima_actualizacion": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "usuario": usuario
        }
        
        # Si hay registro de cambios, añadirlo
        if cambios:
            datos["cambios"] = cambios
        
        # Guardar en archivo JSON
        with open("inventario.json", "w") as f:
            json.dump(datos, f, indent=4)
        
        return True
    except Exception as e:
        st.error(f"Error al guardar el inventario: {e}")
        return False

@cache_decorator(ttl=600)  # Caché de 10 minutos para el inventario
def cargar_inventario():
    try:
        # Verificar si el archivo existe
        if os.path.exists("inventario.json"):
            # Cargar desde archivo JSON
            with open("inventario.json", "r") as f:
                datos = json.load(f)
            
            # Verificar estructura
            if "inventario" in datos:
                return datos["inventario"], datos.get("ultima_actualizacion", "Desconocida")
    except Exception as e:
        st.warning(f"Error al cargar el inventario desde archivo: {e}")
    
    # Valores predeterminados si no se puede cargar - usar diccionario por comprensión más eficiente
    partes_unicas = list(catalogo['Parte'].unique())
    return dict.fromkeys(partes_unicas, 0), "Nuevo"

def sincronizar_inventario(inventario_actual):
    """Sincroniza el inventario con el catálogo actual, añadiendo nuevas partes 
    y eliminando las que ya no existen. Optimizado para rendimiento."""
    
    # Obtener todas las partes actuales del catálogo
    partes_catalogo = set(catalogo['Parte'].unique())
    
    # Obtener todas las partes en el inventario actual
    partes_inventario = set(inventario_actual.keys())
    
    # Cálculos de diferencias en una sola operación
    partes_nuevas = partes_catalogo - partes_inventario
    partes_obsoletas = partes_inventario - partes_catalogo
    
    # Si no hay cambios, devolver rápidamente el inventario original
    if not partes_nuevas and not partes_obsoletas:
        return inventario_actual, False, []
    
    # Crear una copia del inventario para modificarla de manera más eficiente
    inventario_sincronizado = {k: v for k, v in inventario_actual.items() if k not in partes_obsoletas}
    
    # Añadir nuevas partes con valor 0 de manera optimizada
    for parte in partes_nuevas:
        inventario_sincronizado[parte] = 0
    
    # Registrar los cambios
    log = []
    if partes_nuevas:
        partes_nuevas_list = sorted(partes_nuevas)
        log.append(f"Añadidas {len(partes_nuevas)} nuevas partes al inventario:")
        # Limitar la cantidad de partes mostradas si son muchas
        if len(partes_nuevas) > 20:
            for parte in partes_nuevas_list[:10]:
                log.append(f"  - {parte}")
            log.append(f"  - ... y {len(partes_nuevas) - 10} más")
        else:
            for parte in partes_nuevas_list:
                log.append(f"  - {parte}")
    
    if partes_obsoletas:
        partes_obsoletas_list = sorted(partes_obsoletas)
        log.append(f"Eliminadas {len(partes_obsoletas)} partes obsoletas del inventario:")
        # Limitar la cantidad de partes mostradas si son muchas
        if len(partes_obsoletas) > 20:
            for parte in partes_obsoletas_list[:10]:
                log.append(f"  - {parte}")
            log.append(f"  - ... y {len(partes_obsoletas) - 10} más")
        else:
            for parte in partes_obsoletas_list:
                log.append(f"  - {parte}")
    
    return inventario_sincronizado, True, log

# Inicializar o sincronizar el inventario
if 'inventario' not in st.session_state or st.session_state.forzar_sincronizacion:
    inventario_cargado, ultima_act = cargar_inventario()
    
    # Sincronizar con el catálogo actual
    inventario_sincronizado, cambios, log_cambios = sincronizar_inventario(inventario_cargado)
    
    # Si hubo cambios o se forzó la sincronización, guardar el inventario sincronizado
    if cambios or st.session_state.forzar_sincronizacion:
        # Añadir información de causa de la sincronización
        if st.session_state.forzar_sincronizacion and not cambios:
            log_cambios = ["Se detectaron cambios en el catálogo, pero no fue necesario actualizar el inventario."]
        
        # Añadir metadatos
        datos_guardado = {
            "inventario": inventario_sincronizado,
            "ultima_actualizacion": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "usuario": "Sistema (Sincronización automática)",
            "cambios": log_cambios
        }
        
        # Guardar en archivo JSON
        with open("inventario.json", "w") as f:
            json.dump(datos_guardado, f, indent=4)
        
        ultima_act = datos_guardado["ultima_actualizacion"]
        
        # Si hubo cambios significativos, mostrar notificación
        if cambios:
            st.toast("El inventario se ha sincronizado con el catálogo actualizado", icon="🔄")
    
    st.session_state.inventario = inventario_sincronizado
    st.session_state.ultima_actualizacion = ultima_act
    
    # Restablecer el flag de sincronización forzada
    if st.session_state.forzar_sincronizacion:
        st.session_state.forzar_sincronizacion = False

if 'temp_inventario' not in st.session_state:
    st.session_state.temp_inventario = st.session_state.inventario.copy()

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

# Función para identificar parejas LH/RH (mejorada para considerar todos los grupos)
@lru_cache(maxsize=32)
def identificar_parejas(partes_tuple):
    partes = list(partes_tuple)
    parejas = {}
    
    # Para cada parte, extraer el nombre base (sin LH/RH)
    for parte in partes:
        # Verificar si es LH o RH
        if " LH" in parte or " RH" in parte:
            # Extraer el nombre base quitando solo la marca LH/RH, no toda la palabra
            if " LH" in parte:
                base_name = parte.replace(" LH", "")
            else:
                base_name = parte.replace(" RH", "")
                
            # Asignar al grupo correcto
            if base_name not in parejas:
                parejas[base_name] = []
            parejas[base_name].append(parte)
    
    # No filtrar por pares completos, incluir todos los grupos
    # para manejar casos donde hay múltiples LH/RH para el mismo componente base
    return parejas

# Calcular métricas (optimizado y corregido para manejar partes en diferentes máquinas)
def calcular_metricas(catalogo, inventario):
    # Crear una copia del catálogo para no modificar el original
    df = catalogo.copy()
    
    # Convertir a numpy para cálculos más rápidos
    parte_series = df['Parte']
    
    # Crear vectores para cálculos
    inventario_array = pd.Series(inventario).loc[parte_series].values
    objetivo_array = df['Objetivo'].values
    stdpack_array = df['StdPack'].values
    rate_array = df['Rate'].values
    
    # Calcular directamente sin apply
    df['Inventario'] = inventario_array
    
    # Calcular faltante
    faltante_array = objetivo_array - inventario_array
    faltante_array = np.maximum(faltante_array, 0)  # Más eficiente que max()
    df['Faltante'] = faltante_array
    
    # Calcular cajas necesarias
    cajas_array = faltante_array / stdpack_array
    df['CajasNecesarias'] = np.ceil(np.where(cajas_array > 0, cajas_array, 0)).astype(int)
    
    # Calcular tiempo necesario (horas)
    df['TiempoNecesario'] = np.divide(faltante_array, rate_array, out=np.zeros_like(faltante_array, dtype=float), where=rate_array!=0)
    
    # Crear un mapeo de todas las partes a su grupo base (sin considerar LH/RH)
    todas_las_partes = tuple(df['Parte'].unique())
    todos_los_grupos = identificar_parejas(todas_las_partes)
    
    # Crear diccionario de mapeo para todas las partes
    parte_a_grupo = {}
    for parte in df['Parte']:
        parte_a_grupo[parte] = parte  # Por defecto, cada parte es su propio grupo
    
    # Aplicar mapeo de grupos - ahora considerando todas las partes, no solo las que tienen faltante
    for base_name, parts in todos_los_grupos.items():
        for part in parts:
            parte_a_grupo[part] = base_name
    
    # Aplicar directamente el mapeo de grupos a todo el DataFrame
    df['GrupoParte'] = df['Parte'].map(parte_a_grupo)
    
    # Filtrar para partes con faltante más eficientemente
    mask_faltante = faltante_array > 0
    if mask_faltante.any():
        df_temp = df[mask_faltante].copy()
        
        # Nota: Ya tenemos el GrupoParte asignado para todas las partes
        
        # Calcular prioridades por grupo y máquina
        # Importante: ahora agrupamos SOLO por GrupoParte y no por (GrupoParte, Maquina)
        # para manejar casos donde el mismo grupo aparece en diferentes máquinas
        tiempo_por_grupo = df_temp.groupby(['GrupoParte'])['TiempoNecesario'].max().reset_index()
        
        # Unir la información de máquina nuevamente
        tiempo_por_grupo = tiempo_por_grupo.merge(
            df_temp[['GrupoParte', 'Maquina']].drop_duplicates(),
            on='GrupoParte',
            how='left'
        )
        
        # Asignar prioridades de forma vectorizada por máquina
        prioridad_por_maquina = {}
        for maquina in df['Maquina'].unique():
            # Filtrar por máquina y ordenar
            maquina_grupos = tiempo_por_grupo[tiempo_por_grupo['Maquina'] == maquina]
            if not maquina_grupos.empty:
                maquina_grupos_sorted = maquina_grupos.sort_values('TiempoNecesario', ascending=False)
                # Asignar prioridades
                for i, (_, row) in enumerate(maquina_grupos_sorted.iterrows()):
                    prioridad_por_maquina[(row['GrupoParte'], maquina)] = i + 1
        
        # Asignar prioridades al DataFrame temporal
        df_temp['Prioridad'] = df_temp.apply(
            lambda row: prioridad_por_maquina.get((row['GrupoParte'], row['Maquina']), None),
            axis=1
        )
        
        # Convertir a tipo numérico para evitar problemas de tipos mixtos
        df_temp['Prioridad'] = pd.to_numeric(df_temp['Prioridad'], errors='coerce')
        
        # Transferir prioridades al DataFrame principal para las partes con faltante
        df.loc[mask_faltante, 'Prioridad'] = df_temp['Prioridad'].values
    else:
        # Asignar valores NaN en lugar de None para mejor compatibilidad
        df['Prioridad'] = np.nan
    
    return df

# Calcular métricas basadas en inventario actual
df_metricas = calcular_metricas(catalogo, st.session_state.inventario)

# Contenido principal basado en la página seleccionada
if st.session_state.page == 'dashboard':
    # PÁGINA PRINCIPAL - DASHBOARD
    st.header("📊 Dashboard por Máquina")
    
    # Mostrar información sobre la última actualización
    if hasattr(st.session_state, 'ultima_actualizacion'):
        if st.session_state.ultima_actualizacion != "Nuevo":
            try:
                # Cargar datos completos para mostrar usuario
                with open("inventario.json", "r") as f:
                    datos = json.load(f)
                usuario = datos.get("usuario", "Sistema")
                fecha = datos.get("ultima_actualizacion", st.session_state.ultima_actualizacion)
                st.caption(f"📅 Última actualización: {fecha} por {usuario}")
            except:
                st.caption(f"📅 Última actualización: {st.session_state.ultima_actualizacion}")

    # Crear una fila para cada máquina
    for maquina in maquinas:
        st.subheader(f"Máquina: {maquina}")
        
        # Filtrar partes para esta máquina
        df_maquina = df_metricas[df_metricas['Maquina'] == maquina].copy()
        
        # Si hay partes con faltante para esta máquina
        df_faltante = df_maquina[df_maquina['Faltante'] > 0].copy()
        
        if not df_faltante.empty:
            # Agrupar por GrupoParte para mostrar los sets juntos
            grupos_partes = df_faltante['GrupoParte'].unique()
            
            # Ordenar por prioridad primero, luego por número de parte más bajo
            prioridades = {}
            for grupo in grupos_partes:
                # Filtrar por grupo (ahora el grupo incluye todas las LH y RH)
                partes_grupo = df_faltante[df_faltante['GrupoParte'] == grupo]
                if not partes_grupo.empty:
                    # Guardar prioridad y nombre más corto para ordenar de forma intuitiva
                    prioridades[grupo] = (
                        partes_grupo['Prioridad'].iloc[0],  # Prioridad
                        min(partes_grupo['Parte'].tolist())  # Parte más baja lexicográficamente
                    )
            
            # Ordenar grupos por prioridad primero, luego por nombre
            grupos_ordenados = sorted(prioridades.items(), key=lambda x: (x[1][0], x[1][1]))
            
            # Tomar el grupo con mayor prioridad
            grupo_prioritario = grupos_ordenados[0][0]
            
            # Filtrar las partes de este grupo SOLO para esta máquina
            # (importante para manejar el caso especial de piezas que pueden estar en múltiples máquinas)
            partes_grupo_prioritario = df_faltante[df_faltante['GrupoParte'] == grupo_prioritario]
            
            # Ordenar las partes primero por LH/RH (para que aparezcan juntas) y luego alfabéticamente
            def orden_personalizado(parte):
                if " LH" in parte:
                    return (parte.replace(" LH", ""), 0)
                elif " RH" in parte:
                    return (parte.replace(" RH", ""), 1)
                return (parte, 2)
            
            # Ordenar con la función personalizada
            partes_grupo_prioritario = partes_grupo_prioritario.copy()
            partes_grupo_prioritario['orden'] = partes_grupo_prioritario['Parte'].apply(orden_personalizado)
            partes_grupo_prioritario = partes_grupo_prioritario.sort_values('orden')
            
            # Mostrar también el siguiente grupo en la cola (si existe)
            has_next_group = len(grupos_ordenados) > 1
            next_group = None
            partes_siguiente_grupo = None
            if has_next_group:
                next_grupo_prioritario = grupos_ordenados[1][0]
                partes_siguiente_grupo = df_faltante[df_faltante['GrupoParte'] == next_grupo_prioritario].sort_values('Parte')
            
            # Cabecera con el nombre base del grupo
            if "LH" in partes_grupo_prioritario['Parte'].iloc[0] or "RH" in partes_grupo_prioritario['Parte'].iloc[0]:
                nombre_base = grupo_prioritario
                st.markdown(f"### Set: **{nombre_base}**")
                prioridad_valor = partes_grupo_prioritario['Prioridad'].iloc[0]
                prioridad_display = int(prioridad_valor) if pd.notnull(prioridad_valor) else '-'
                st.markdown(f"**Prioridad:** {prioridad_display}")
                
                # Mostrar información del inventario en una caja destacada
                inventario_total = partes_grupo_prioritario['Inventario'].sum()
                objetivo_total = partes_grupo_prioritario['Objetivo'].sum()
                
                st.info(f"📦 **Inventario Actual Total:** {int(inventario_total)} piezas de {int(objetivo_total)} objetivo")
                
                # Crear una tabla para el set
                data_set = []
                
                for _, parte in partes_grupo_prioritario.iterrows():
                    lado = "Izquierdo (LH)" if "LH" in parte['Parte'] else "Derecho (RH)"
                    data_set.append({
                        "Parte": parte['Parte'],
                        "Lado": lado,
                        "Inventario": int(parte['Inventario']),
                        "Objetivo": int(parte['Objetivo']),
                        "Faltante": int(parte['Faltante']),
                        "Cajas": int(parte['CajasNecesarias'])
                    })
                
                # Convertir a DataFrame para mostrar como tabla
                df_set = pd.DataFrame(data_set)
                st.table(df_set)
                
                # Calcular tiempo total (usar el máximo)
                tiempo_max = partes_grupo_prioritario['TiempoNecesario'].max()
                st.metric("Tiempo total necesario (horas)", f"{tiempo_max:.2f}")
            
            else:
                # Si no es un par LH/RH, mostrar como antes
                parte_asignada = partes_grupo_prioritario.iloc[0]
                
                # Crear columnas para mostrar la información
                col1, col2, col3 = st.columns(3)
                
                # Mostrar el nombre completo del producto (sin truncar)
                with col1:
                    st.write("**Producto:**")
                    st.write(f"**{parte_asignada['Parte']}**")
                    
                with col2:
                    st.metric("Objetivo", f"{int(parte_asignada['Objetivo'])}")
                    
                with col3:
                    st.metric("Cajas a Correr", f"{int(parte_asignada['CajasNecesarias'])}")
                
                # Mostrar inventario y tiempo en columnas
                col1, col2 = st.columns(2)
                
                with col1:
                    # Mostrar inventario con color basado en el nivel
                    inventario = int(parte_asignada['Inventario'])
                    objetivo = int(parte_asignada['Objetivo'])
                    porcentaje = (inventario / objetivo * 100) if objetivo > 0 else 0
                    
                    if porcentaje >= 75:
                        st.success(f"📦 **Inventario:** {inventario} piezas ({porcentaje:.1f}%)")
                    elif porcentaje >= 35:
                        st.warning(f"📦 **Inventario:** {inventario} piezas ({porcentaje:.1f}%)")
                    else:
                        st.error(f"📦 **Inventario:** {inventario} piezas ({porcentaje:.1f}%)")
                
                with col2:
                    st.metric("Tiempo (horas)", f"{parte_asignada['TiempoNecesario']:.2f}")
                
                # Mostrar prioridad con un indicador visual
                prioridad_valor = parte_asignada['Prioridad']
                prioridad_display = int(prioridad_valor) if pd.notnull(prioridad_valor) else '-'
                st.write(f"**Prioridad:** {prioridad_display}")
            
            # Barra de progreso para visualizar el avance hacia el objetivo para el grupo
            inventario_promedio = partes_grupo_prioritario['Inventario'].mean()
            objetivo_promedio = partes_grupo_prioritario['Objetivo'].mean()
            progreso = min(100, (inventario_promedio / objetivo_promedio) * 100) if objetivo_promedio > 0 else 0
            
            # Definir color de la barra de progreso según el nivel
            if progreso >= 75:
                st.markdown("""
                <style>
                    .stProgress > div > div {
                        background-color: #0c0;
                    }
                </style>""", unsafe_allow_html=True)
            elif progreso >= 35:
                st.markdown("""
                <style>
                    .stProgress > div > div {
                        background-color: #fc0;
                    }
                </style>""", unsafe_allow_html=True)
            else:
                st.markdown("""
                <style>
                    .stProgress > div > div {
                        background-color: #f00;
                    }
                </style>""", unsafe_allow_html=True)
                
            st.progress(progreso / 100)
            
            # Mostrar información del siguiente grupo (si existe)
            if has_next_group and partes_siguiente_grupo is not None and not partes_siguiente_grupo.empty:
                st.markdown("---")
                st.markdown("### 🔄 Siguiente en la cola")
                
                # Obtener el nombre base del siguiente grupo
                siguiente_nombre_base = next_grupo_prioritario
                siguiente_prioridad = partes_siguiente_grupo['Prioridad'].iloc[0]
                
                # Cabecera con datos básicos
                st.markdown(f"**Set:** {siguiente_nombre_base}")
                prioridad_display = int(siguiente_prioridad) if pd.notnull(siguiente_prioridad) else '-'
                st.markdown(f"**Prioridad:** {prioridad_display}")
                
                # Mostrar inventario del siguiente grupo
                siguiente_inventario_total = partes_siguiente_grupo['Inventario'].sum()
                siguiente_objetivo_total = partes_siguiente_grupo['Objetivo'].sum()
                siguiente_tiempo_max = partes_siguiente_grupo['TiempoNecesario'].max()
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.info(f"📦 **Inventario:** {int(siguiente_inventario_total)} piezas")
                with col2:
                    st.info(f"⏱ **Tiempo:** {siguiente_tiempo_max:.2f} horas")
                with col3:
                    st.info(f"📊 **Cajas:** {int(partes_siguiente_grupo['CajasNecesarias'].sum())}")
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
        
        # Obtener todas las partes y ordenarlas alfabéticamente
        partes_unicas = sorted(catalogo['Parte'].unique())
            
        # Crear columnas para mostrar las partes
        container = st.container()
        
        # Dividir las partes en dos columnas para mejor visualización
        mitad = len(partes_unicas) // 2
        
        # Primera columna
        with col1:
            for parte in partes_unicas[:mitad]:
                st.session_state.temp_inventario[parte] = st.number_input(
                    f"{parte}", 
                    min_value=0, 
                    value=st.session_state.inventario[parte],
                    key=f"inv_{parte}",
                    help=f"Estándar: {catalogo[catalogo['Parte'] == parte]['StdPack'].iloc[0]}, Objetivo: {catalogo[catalogo['Parte'] == parte]['Objetivo'].iloc[0]}"
                )
            
        # Segunda columna
        with col2:
            for parte in partes_unicas[mitad:]:
                st.session_state.temp_inventario[parte] = st.number_input(
                    f"{parte}", 
                    min_value=0, 
                    value=st.session_state.inventario[parte],
                    key=f"inv2_{parte}",
                    help=f"Estándar: {catalogo[catalogo['Parte'] == parte]['StdPack'].iloc[0]}, Objetivo: {catalogo[catalogo['Parte'] == parte]['Objetivo'].iloc[0]}"
                )        # Campos para registrar usuario que realiza el cambio
        if 'ultimo_usuario' not in st.session_state:
            st.session_state.ultimo_usuario = ""
            
        usuario = st.text_input("Su Nombre (para registro de cambios)", 
                               value=st.session_state.ultimo_usuario,
                               key="nombre_usuario_actual")
        
        # Botón para guardar cambios
        submitted = st.form_submit_button("Guardar Cambios")
        
        if submitted:
            if not usuario.strip():
                st.warning("Por favor ingrese su nombre para registrar el cambio")
            else:
                # Guardar temporalmente el nombre de usuario
                st.session_state.ultimo_usuario = usuario
                
                # Detectar cambios en el inventario
                cambios_inventario = []
                for parte, nuevo_valor in st.session_state.temp_inventario.items():
                    if parte in st.session_state.inventario:
                        valor_anterior = st.session_state.inventario.get(parte, 0)
                        if nuevo_valor != valor_anterior:
                            cambio = nuevo_valor - valor_anterior
                            signo = "+" if cambio > 0 else ""
                            cambios_inventario.append(f"Parte {parte}: {valor_anterior} → {nuevo_valor} ({signo}{cambio})")
                
                # Actualizar inventario en session_state
                st.session_state.inventario = st.session_state.temp_inventario.copy()
                
                # Guardar en archivo persistente con registro de cambios
                datos_guardado = {
                    "inventario": st.session_state.inventario,
                    "ultima_actualizacion": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "usuario": usuario
                }
                
                # Añadir cambios al registro si los hubo
                if cambios_inventario:
                    datos_guardado["cambios"] = [f"Actualización manual del inventario:"] + cambios_inventario
                
                with open("inventario.json", "w") as f:
                    json.dump(datos_guardado, f, indent=4)
                
                st.session_state.ultima_actualizacion = datos_guardado["ultima_actualizacion"]
                
                st.success(f"✅ Inventario actualizado correctamente por {usuario}")
                # Borrar el usuario después de guardar cambios
                st.session_state.ultimo_usuario = ""
                
                # Volver automáticamente al dashboard después de actualizar
                st.session_state.page = 'dashboard'
                st.rerun()
    
    # Botón para cancelar y volver al dashboard
    if st.button("Cancelar"):
        # También borrar el usuario al cancelar
        st.session_state.ultimo_usuario = ""
        st.session_state.page = 'dashboard'
        st.rerun()

elif st.session_state.page == 'admin' and st.session_state.is_admin:
    # PÁGINA DE ADMINISTRADOR
    st.header("🔐 Panel de Administrador")
    
    # Crear pestañas para diferentes secciones del panel de administrador
    tab1, tab2, tab3 = st.tabs(["📋 Tabla General", "📅 Plan Semanal de Producción", "📝 Registro de Cambios"])
    
    with tab1:
        # Tabla completa con todos los cálculos
        st.subheader("📋 Tabla General de Producción")
        
        # Selector de máquina y búsqueda
        col_maquina, col_busqueda = st.columns([1, 2])
        
        with col_maquina:
            maquina_seleccionada = st.selectbox(
                "Seleccionar máquina",
                ["Todas"] + list(maquinas),
                index=0
            )
        
        with col_busqueda:
            busqueda_parte = st.text_input("Buscar parte:", key="busqueda_tabla")
    
    # Preparar la tabla para mostrar de manera más eficiente
    df_tabla = df_metricas.copy()
    
    # Aplicar filtros
    if maquina_seleccionada != "Todas":
        df_tabla = df_tabla[df_tabla['Maquina'] == maquina_seleccionada]
    
    if busqueda_parte:
        # Filtro de búsqueda case-insensitive
        mascara_busqueda = df_tabla['Parte'].str.lower().str.contains(busqueda_parte.lower())
        df_tabla = df_tabla[mascara_busqueda]
    
    # Ordenar por máquina y prioridad más eficientemente
    # Convertir temporalmente prioridad a numérico para ordenar correctamente
    df_tabla['Prioridad_temp'] = pd.to_numeric(df_tabla['Prioridad'], errors='coerce')
    orden = ['Maquina', 'Prioridad_temp', 'GrupoParte']
    df_tabla = df_tabla.sort_values(orden, na_position='last')
    df_tabla = df_tabla.drop('Prioridad_temp', axis=1)
    
    # Convertir Prioridad a formato mixto (entero o '-')
    df_tabla['Prioridad'] = df_tabla['Prioridad'].apply(
        lambda x: int(x) if pd.notnull(x) and str(x).replace('.', '', 1).isdigit() else '-'
    )
    
    # Formatear columnas numéricas más eficientemente
    columnas_enteras = ['Inventario', 'Objetivo', 'Faltante', 'CajasNecesarias']
    for col in columnas_enteras:
        df_tabla[col] = df_tabla[col].astype('int32')  # Usar int32 en lugar de int64 para ahorrar memoria
    
    df_tabla['TiempoNecesario'] = df_tabla['TiempoNecesario'].round(2)
    
    # Columnas a mostrar - optimizar para mostrar datos relevantes
    columnas_mostrar = [
        'Parte', 'GrupoParte', 'Maquina', 'Inventario', 'Objetivo', 
        'Faltante', 'StdPack', 'CajasNecesarias', 
        'Rate', 'TiempoNecesario', 'Prioridad'
    ]
    
    # Opción para filtrar solo partes con faltante
    mostrar_solo_faltantes = st.checkbox("Mostrar solo partes con faltante", value=False)
    if mostrar_solo_faltantes:
        df_tabla = df_tabla[df_tabla['Faltante'] > 0]
    
    # Mostrar la tabla
    st.dataframe(
        df_tabla[columnas_mostrar], 
        use_container_width=True,
        hide_index=True
    )
    
    # Mostrar también la vista de sets
    st.subheader("📋 Vista por Sets")
    
    # Botón para alternar la vista agrupada
    show_grouped = st.checkbox("Mostrar agrupado por sets", value=True)
    
    if show_grouped:
        # Filtrar por máquina si se seleccionó una específica
        df_para_agrupar = df_tabla
        
        # Convertir temporalmente la prioridad a numérico para evitar errores en la agrupación
        # Guardar los valores originales para restaurarlos después
        prioridades_originales = df_para_agrupar['Prioridad'].copy()
        
        # Reemplazar valores no numéricos con NaN
        df_para_agrupar['Prioridad'] = pd.to_numeric(df_para_agrupar['Prioridad'], errors='coerce')
        
        # Agrupar por GrupoParte y Máquina
        df_grouped = df_para_agrupar.groupby(['GrupoParte', 'Maquina']).agg({
            'Inventario': 'mean',
            'Objetivo': 'mean',
            'Faltante': 'sum',
            'CajasNecesarias': 'sum',
            'TiempoNecesario': 'max',
            'Prioridad': 'min'  # Ahora es seguro aplicar min() ya que todos son valores numéricos o NaN
        }).reset_index()
        
        # Formatear columnas numéricas
        df_grouped['Inventario'] = df_grouped['Inventario'].astype(int)
        df_grouped['Objetivo'] = df_grouped['Objetivo'].astype(int)
        df_grouped['Faltante'] = df_grouped['Faltante'].astype(int)
        df_grouped['CajasNecesarias'] = df_grouped['CajasNecesarias'].astype(int)
        df_grouped['TiempoNecesario'] = df_grouped['TiempoNecesario'].round(2)
        
        # Ordenar por máquina y prioridad
        df_grouped = df_grouped.sort_values(['Maquina', 'Prioridad'], na_position='last')
        
        # Restaurar el formato de la prioridad para mostrar correctamente
        df_grouped['Prioridad'] = df_grouped['Prioridad'].map(lambda x: int(x) if pd.notnull(x) else '-')
        
        # Columnas a mostrar
        columnas_grouped = [
            'GrupoParte', 'Maquina', 'Inventario', 'Objetivo', 
            'Faltante', 'CajasNecesarias', 'TiempoNecesario', 'Prioridad'
        ]
        
        # Mostrar la tabla agrupada
        st.dataframe(
            df_grouped[columnas_grouped], 
            use_container_width=True,
            hide_index=True
        )
        
        # Añadir vista de secuencia de producción por máquina
        st.subheader("🔄 Secuencia de Producción por Máquina")
        
        # Mostrar la secuencia de producción para cada máquina
        for maquina in maquinas:
            if maquina_seleccionada == "Todas" or maquina_seleccionada == maquina:
                # Filtrar grupos para esta máquina
                df_maquina_grupos = df_grouped[df_grouped['Maquina'] == maquina]
                
                if not df_maquina_grupos.empty:
                    # Convertir temporalmente a numérico para ordenar correctamente
                    df_maquina_grupos['Prioridad_temp'] = pd.to_numeric(df_maquina_grupos['Prioridad'], errors='coerce')
                    # Ordenar por prioridad numérica
                    df_maquina_grupos = df_maquina_grupos.sort_values('Prioridad_temp')
                    df_maquina_grupos = df_maquina_grupos.drop('Prioridad_temp', axis=1)
                    
                    st.write(f"### Máquina: {maquina}")
                    
                    # Crear lista ordenada con los grupos y sus métricas principales
                    for i, (_, grupo) in enumerate(df_maquina_grupos.iterrows()):
                        if pd.notna(grupo['Prioridad']) and grupo['Prioridad'] != '-':
                            prioridad_valor = grupo['Prioridad']
                            prioridad_display = int(prioridad_valor) if pd.notnull(prioridad_valor) and prioridad_valor != '-' else '-'
                            st.write(f"**{i+1}. {grupo['GrupoParte']}** - Prioridad: {prioridad_display} - Tiempo: {grupo['TiempoNecesario']:.2f} horas - Cajas: {int(grupo['CajasNecesarias'])}")
                    
                    st.divider()
    
    # Información sobre el último cálculo
    st.caption("La prioridad se calcula según el tiempo necesario para alcanzar el objetivo.")
    
    with tab2:
        # Pestaña de plan semanal de producción
        st.subheader("📅 Simulación de Plan Semanal de Producción")
        
        # Definir la capacidad disponible por máquina
        CAPACIDAD_SEMANAL = 22.5 * 5.6  # 22.5 horas por 5.6 días
        TIEMPO_CAMBIO = 1.0  # 1 hora por cambio de producto
        
        # Extraer solo números de las máquinas
        numeros_transfer = [m.split()[1] if len(m.split()) > 1 else m for m in maquinas]
        
        # Crear selector de máquina
        indice_maquina = st.selectbox(
            "Seleccionar número de transfer para planear producción",
            range(len(numeros_transfer)),
            format_func=lambda i: numeros_transfer[i],
            key="maquina_capacidad"
        )
        
        # Obtener la máquina seleccionada
        maquina_cap = maquinas[indice_maquina]
        
        st.info("Esta es una herramienta de simulación para planificar la producción semanal. Los valores ingresados no afectarán el inventario real.")
        
        # Filtrar datos para la máquina seleccionada
        df_maquina_cap = df_metricas[df_metricas['Maquina'] == maquina_cap].copy()
        
        # Obtener grupos de partes únicos para esta máquina
        grupos_unicos = sorted(df_maquina_cap['GrupoParte'].unique())
        
        # Crear un DataFrame para la simulación
        df_simulacion = pd.DataFrame({
            'GrupoParte': grupos_unicos
        })
        
        # Añadir información de cada grupo
        for grupo in grupos_unicos:
            partes_grupo = df_maquina_cap[df_maquina_cap['GrupoParte'] == grupo]
            df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'StdPack'] = partes_grupo['StdPack'].iloc[0]
            df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'Rate'] = partes_grupo['Rate'].iloc[0]
            df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'Inventario'] = partes_grupo['Inventario'].mean()
            df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'Objetivo'] = partes_grupo['Objetivo'].mean()
            df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'Faltante'] = partes_grupo['Faltante'].mean()
            df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'Prioridad'] = partes_grupo['Prioridad'].iloc[0]
            
        # Generar plan automáticamente basado en lógica de prioridades
        with st.form("plan_semanal_form"):
            st.write("Configuración del plan de producción:")
            
            col1, col2 = st.columns(2)
            with col1:
                tipo_plan = st.radio(
                    "Tipo de plan a generar:",
                    ["Basado en faltantes", "Basado en prioridad", "Producción mínima para todos"],
                    index=0
                )
                
            with col2:
                dias_produccion = st.slider("Días de producción", 1, 5, 5)
                horas_por_dia = st.number_input("Horas efectivas por día", min_value=1.0, max_value=24.0, value=22.5)
            
            # Calcular capacidad disponible
            capacidad_disponible = dias_produccion * horas_por_dia
            
            # Generar plan automáticamente al enviar el formulario
            submitted = st.form_submit_button("Generar Plan de Producción")
            
            if submitted:
                # Inicializar diccionario para cantidades
                cantidades_plan = {}
                
                # Lógica para determinar las cantidades según el tipo de plan
                if tipo_plan == "Basado en faltantes":
                    # Ordenar por faltante mayor a menor
                    df_plan = df_simulacion.sort_values('Faltante', ascending=False)
                    
                    # Asignar producción según faltantes
                    tiempo_asignado = 0
                    for idx, row in df_plan.iterrows():
                        if tiempo_asignado >= capacidad_disponible:
                            cantidades_plan[row['GrupoParte']] = 0
                            continue
                            
                        faltante = max(0, row['Faltante'])
                        std_pack = row['StdPack']
                        rate = row['Rate']
                        
                        # Calcular cantidad redondeando al std_pack más cercano
                        cantidad_raw = faltante
                        cantidad = int(np.ceil(cantidad_raw / std_pack) * std_pack)
                        
                        # Calcular tiempo necesario
                        tiempo_necesario = cantidad / rate
                        
                        # Si el tiempo excede lo disponible, ajustar
                        if tiempo_asignado + tiempo_necesario > capacidad_disponible:
                            tiempo_restante = capacidad_disponible - tiempo_asignado
                            cantidad = int(np.floor(tiempo_restante * rate / std_pack) * std_pack)
                            if cantidad <= 0:
                                cantidad = 0
                                
                        cantidades_plan[row['GrupoParte']] = cantidad
                        tiempo_asignado += cantidad / rate + (1.0 if cantidad > 0 else 0)  # Sumar tiempo de cambio si hay producción
                
                elif tipo_plan == "Basado en prioridad":
                    # Convertir prioridad a numérico para ordenar correctamente
                    df_simulacion['Prioridad_num'] = pd.to_numeric(df_simulacion['Prioridad'], errors='coerce')
                    
                    # Ordenar por prioridad (menor número es más prioritario)
                    df_plan = df_simulacion.sort_values('Prioridad_num', ascending=True)
                    
                    # Asignar producción según prioridad
                    tiempo_asignado = 0
                    for idx, row in df_plan.iterrows():
                        if tiempo_asignado >= capacidad_disponible:
                            cantidades_plan[row['GrupoParte']] = 0
                            continue
                            
                        faltante = max(0, row['Faltante'])
                        std_pack = row['StdPack']
                        rate = row['Rate']
                        
                        # Calcular cantidad redondeando al std_pack más cercano
                        cantidad_raw = faltante
                        cantidad = int(np.ceil(cantidad_raw / std_pack) * std_pack)
                        
                        # Calcular tiempo necesario
                        tiempo_necesario = cantidad / rate
                        
                        # Si el tiempo excede lo disponible, ajustar
                        if tiempo_asignado + tiempo_necesario > capacidad_disponible:
                            tiempo_restante = capacidad_disponible - tiempo_asignado
                            cantidad = int(np.floor(tiempo_restante * rate / std_pack) * std_pack)
                            if cantidad <= 0:
                                cantidad = 0
                                
                        cantidades_plan[row['GrupoParte']] = cantidad
                        tiempo_asignado += cantidad / rate + (1.0 if cantidad > 0 else 0)  # Sumar tiempo de cambio si hay producción
                
                else:  # Producción mínima para todos
                    # Priorizar productos con faltante
                    df_con_faltante = df_simulacion[df_simulacion['Faltante'] > 0].copy()
                    
                    if not df_con_faltante.empty:
                        # Calcular producción proporcional
                        tiempo_total_requerido = sum([f / r + 1.0 for f, r in zip(df_con_faltante['Faltante'], df_con_faltante['Rate'])])
                        factor_ajuste = min(1.0, capacidad_disponible / tiempo_total_requerido if tiempo_total_requerido > 0 else 1.0)
                        
                        for idx, row in df_con_faltante.iterrows():
                            faltante = max(0, row['Faltante'])
                            std_pack = row['StdPack']
                            rate = row['Rate']
                            
                            # Calcular producción proporcional
                            cantidad_raw = faltante * factor_ajuste
                            cantidad = int(np.ceil(cantidad_raw / std_pack) * std_pack)
                            
                            cantidades_plan[row['GrupoParte']] = cantidad
                            
                        # Para productos sin faltante, asignar 0
                        for grupo in grupos_unicos:
                            if grupo not in cantidades_plan:
                                cantidades_plan[grupo] = 0
                    else:
                        # Si no hay faltantes, asignar una cantidad mínima a todos
                        tiempo_por_grupo = capacidad_disponible / len(grupos_unicos)
                        
                        for grupo in grupos_unicos:
                            std_pack = df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'StdPack'].iloc[0]
                            rate = df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'Rate'].iloc[0]
                            
                            # Calcular cantidad según tiempo disponible
                            cantidad_raw = tiempo_por_grupo * rate
                            cantidad = int(np.floor(cantidad_raw / std_pack) * std_pack)
                            
                            cantidades_plan[grupo] = cantidad
                
                # Guardar el plan en la sesión
                st.session_state.cantidades_plan = cantidades_plan
                st.session_state.capacidad_disponible = capacidad_disponible
        
        if submitted or 'cantidades_plan' in st.session_state:
            # Guardar los valores en session_state para mantenerlos después de la sumisión
            if submitted:
                st.session_state.cantidades_plan = cantidades_plan
            else:
                cantidades_plan = st.session_state.cantidades_plan
            
            # Añadir cantidades al DataFrame
            for grupo, cantidad in cantidades_plan.items():
                df_simulacion.loc[df_simulacion['GrupoParte'] == grupo, 'Cantidad'] = cantidad
            
            # Calcular tiempos
            df_simulacion['Tiempo Produccion'] = df_simulacion['Cantidad'] / df_simulacion['Rate']
            
            # Filtrar solo grupos con producción planeada
            df_simulacion_filtrado = df_simulacion[df_simulacion['Cantidad'] > 0].copy()
            
            # Calcular grupos de producto (cada grupo requiere un cambio)
            grupos_a_producir = len(df_simulacion_filtrado)
            tiempo_cambios = grupos_a_producir * TIEMPO_CAMBIO
            
            # Añadir tiempo de cambio a cada grupo
            df_simulacion_filtrado['Tiempo Cambio'] = TIEMPO_CAMBIO
            df_simulacion_filtrado['Tiempo Total'] = df_simulacion_filtrado['Tiempo Produccion'] + df_simulacion_filtrado['Tiempo Cambio']
            
            # Calcular tiempo total necesario para la producción
            tiempo_total_produccion = df_simulacion_filtrado['Tiempo Produccion'].sum()
            
            # Calcular tiempo total incluyendo cambios
            tiempo_total = tiempo_total_produccion + tiempo_cambios
        
        # Mostrar resultados
        if 'cantidades_plan' in st.session_state:
            # Usar capacidad personalizada si está definida
            capacidad_usar = st.session_state.capacidad_disponible if 'capacidad_disponible' in st.session_state else CAPACIDAD_SEMANAL
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Capacidad Disponible", f"{capacidad_usar:.1f} hrs")
            with col2:
                st.metric("Tiempo de Producción", f"{tiempo_total_produccion:.1f} hrs")
            with col3:
                st.metric("Tiempo de Cambios", f"{tiempo_cambios:.1f} hrs ({grupos_a_producir} cambios)")
            
            # Calcular porcentaje de utilización
            porcentaje_utilizacion = (tiempo_total / capacidad_usar) * 100
            
            # Mostrar gráfico de utilización
            st.subheader("Utilización de Capacidad")
            
            # Determinar color según utilización
            if porcentaje_utilizacion > 100:
                color_barra = "red"
                mensaje = "⚠️ **SOBRECAPACIDAD**: La máquina no tiene suficiente tiempo para completar toda la producción"
            elif porcentaje_utilizacion > 85:
                color_barra = "orange"
                mensaje = "⚠️ **ATENCIÓN**: La máquina está operando cerca de su capacidad máxima"
            else:
                color_barra = "green"
                mensaje = "✅ **CAPACIDAD SUFICIENTE**: La máquina tiene capacidad para la producción actual"
            
            # Mostrar barra de progreso personalizada
            st.progress(min(porcentaje_utilizacion / 100, 1.0), text=f"Utilización: {porcentaje_utilizacion:.1f}%")
            st.markdown(mensaje)
            
            # Mostrar tabla de partes a producir
            st.subheader("Detalle del Plan de Producción")
            
            # Mostrar el dataframe con formato
            df_mostrar = df_simulacion_filtrado[['GrupoParte', 'Cantidad', 'Tiempo Produccion', 'Tiempo Cambio', 'Tiempo Total']].copy()
            df_mostrar.columns = ['Grupo de Parte', 'Cantidad', 'Tiempo Producción (hrs)', 'Tiempo Cambio (hrs)', 'Tiempo Total (hrs)']
            
            # Formatear columnas numéricas
            df_mostrar['Tiempo Producción (hrs)'] = df_mostrar['Tiempo Producción (hrs)'].round(2)
            df_mostrar['Tiempo Cambio (hrs)'] = df_mostrar['Tiempo Cambio (hrs)'].round(2)
            df_mostrar['Tiempo Total (hrs)'] = df_mostrar['Tiempo Total (hrs)'].round(2)
            
            st.dataframe(df_mostrar, hide_index=True)
        else:
            st.info("Complete el formulario y haga clic en 'Calcular Plan de Producción' para ver los resultados.")
        
        # Visualización del plan semanal
        if 'cantidades_plan' in st.session_state:
            st.subheader("Visualización del Plan Semanal")
            
            # Obtener los días y turnos necesarios según la configuración
            dias_disponibles = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
            dias = dias_disponibles[:st.session_state.get('dias_produccion', 5)]
            
            # Calcular número de turnos según las horas por día
            horas_por_dia = st.session_state.get('horas_por_dia', 22.5)
            turnos_completos = int(horas_por_dia // 8)
            horas_ultimo_turno = horas_por_dia % 8
            
            turnos = []
            for i in range(turnos_completos):
                turnos.append(f"Turno {i+1}")
                
            if horas_ultimo_turno > 0:
                turnos.append(f"Turno {len(turnos)+1} ({horas_ultimo_turno:.1f}h)")
            
            # Si no hay turnos definidos (caso extremo), crear al menos uno
            if not turnos:
                turnos = ["Turno 1"]
            
            # Horas efectivas por turno
            horas_por_turno = [8] * turnos_completos
            if horas_ultimo_turno > 0:
                horas_por_turno.append(horas_ultimo_turno)
            
            # Datos para visualización
            datos_produccion = []
            
            # Distribuir productos en el calendario según prioridad
            productos_asignados = df_simulacion_filtrado.sort_values(
                'Prioridad', 
                key=lambda x: pd.to_numeric(x, errors='coerce'),
                ascending=True
            ).copy()
            
            # Variables para seguimiento
            tiempo_actual = 0
            dia_actual = 0
            turno_actual = 0
            
            # Recorrer cada producto para distribuirlo en el calendario
            for idx, producto in productos_asignados.iterrows():
                tiempo_producto = producto['Tiempo Total']  # Incluye tiempo de cambio
                tiempo_restante = tiempo_producto
                
                while tiempo_restante > 0 and dia_actual < len(dias):
                    # Calcular cuánto tiempo se puede asignar en el turno actual
                    horas_turno_actual = horas_por_turno[turno_actual]
                    tiempo_usado_turno = tiempo_actual % horas_turno_actual
                    tiempo_disponible_turno = horas_turno_actual - tiempo_usado_turno
                    
                    # No permitir tiempos negativos o cero
                    if tiempo_disponible_turno <= 0:
                        turno_actual += 1
                        if turno_actual >= len(turnos):
                            turno_actual = 0
                            dia_actual += 1
                        tiempo_actual = 0
                        continue
                    
                    tiempo_asignado = min(tiempo_restante, tiempo_disponible_turno)
                    
                    # Añadir entrada al calendario
                    datos_produccion.append({
                        'Dia': dias[dia_actual],
                        'Turno': turnos[turno_actual],
                        'Horas': tiempo_asignado,
                        'Producto': producto['GrupoParte'],
                        'Utilizacion': (tiempo_asignado / horas_turno_actual) * 100
                    })
                    
                    # Actualizar tiempos
                    tiempo_actual += tiempo_asignado
                    tiempo_restante -= tiempo_asignado
                    
                    # Pasar al siguiente turno/día si es necesario
                    if tiempo_actual >= horas_turno_actual:
                        tiempo_actual = 0
                        turno_actual += 1
                        if turno_actual >= len(turnos):
                            turno_actual = 0
                            dia_actual += 1
            
            # Convertir a dataframe
            df_produccion = pd.DataFrame(datos_produccion)
            
            if not df_produccion.empty:
                # Crear gráfico de barras apiladas
                fig = px.bar(
                    df_produccion,
                    x='Dia',
                    y='Horas',
                    color='Producto',
                    facet_row='Turno',
                    title=f'Distribución de la Producción - Transfer {numeros_transfer[indice_maquina]}',
                    labels={'Horas': 'Horas Utilizadas'},
                    category_orders={"Dia": dias, "Turno": turnos},
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                
                fig.update_layout(
                    height=min(600, 200 * len(turnos)),  # Altura ajustada según número de turnos
                    legend_title='Producto',
                )
                
                # Añadir línea de referencia para las horas máximas por turno
                for i, horas_max in enumerate(horas_por_turno):
                    if i < len(turnos):  # Verificar que no nos pasemos del índice máximo
                        fig.add_shape(
                            type="line",
                            x0=-0.5,
                            y0=horas_max,
                            x1=len(dias)-0.5,
                            y1=horas_max,
                            line=dict(color="red", width=2, dash="dot"),
                            row=i+1,
                            col=1
                        )
                
                st.plotly_chart(fig, use_container_width=True)
                
                # Mostrar tabla de distribución por día y turno
                pivot_horas = pd.pivot_table(
                    df_produccion,
                    values='Horas',
                    index='Turno',
                    columns='Dia',
                    fill_value=0,
                    aggfunc='sum'
                ).reset_index()
                
                st.write("### Horas por turno")
                st.dataframe(pivot_horas, hide_index=True)
                
                # Mostrar tabla de distribución por producto, día y turno
                st.write("### Producción detallada")
                st.dataframe(
                    df_produccion[['Dia', 'Turno', 'Producto', 'Horas']].sort_values(['Dia', 'Turno']),
                    hide_index=True
                )
        
        # Sugerir optimizaciones si es necesario
        if 'cantidades_plan' in st.session_state and porcentaje_utilizacion > 100:
            st.subheader("Sugerencias para Optimización")
            capacidad_usar = st.session_state.capacidad_disponible if 'capacidad_disponible' in st.session_state else CAPACIDAD_SEMANAL
            exceso = tiempo_total - capacidad_usar
            st.write(f"Necesitas reducir aproximadamente **{exceso:.1f} horas** para estar dentro de la capacidad disponible.")
            
            # Sugerir eliminar algunos productos según prioridad numérica
            try:
                # Convertir prioridad a numérico para ordenar correctamente
                df_simulacion_filtrado['Prioridad_Num'] = pd.to_numeric(df_simulacion_filtrado['Prioridad'], errors='coerce')
                # Ordenar por prioridad (mayor número = menor prioridad)
                df_candidatos = df_simulacion_filtrado.sort_values('Prioridad_Num', ascending=False)
            except:
                # Si hay error, ordenar por tiempo total
                df_candidatos = df_simulacion_filtrado.sort_values('Tiempo Total', ascending=False)
                
            st.write("Considera mover estos productos a la siguiente semana:")
            
            # Encontrar combinación de productos que sumen cerca del exceso de tiempo
            tiempo_encontrado = 0
            productos_a_mover = []
            
            for i, producto in df_candidatos.iterrows():
                if tiempo_encontrado >= exceso:
                    break
                    
                tiempo_producto = producto['Tiempo Total']
                productos_a_mover.append({
                    'nombre': producto['GrupoParte'],
                    'tiempo': tiempo_producto
                })
                tiempo_encontrado += tiempo_producto
                
                st.write(f"- {producto['GrupoParte']}: {tiempo_producto:.1f} hrs")
                
            st.info(f"Moviendo estos productos liberarías {tiempo_encontrado:.1f} de las {exceso:.1f} horas necesarias.")
    
    with tab3:
        # Mostrar registro de cambios en el catálogo y en el inventario
        st.subheader("📝 Registro de Cambios")
        
        # Botón para forzar sincronización
        if st.button("🔄 Forzar sincronización con catálogo", key="force_sync"):
            st.session_state.forzar_sincronizacion = True
            st.success("Sincronizando inventario con catálogo actualizado...")
            st.rerun()
        
        # Verificar si existe el archivo de inventario
        # Mostrar información sobre el catálogo
        if os.path.exists("catalogo.csv"):
            try:
                # Obtener fecha de modificación del archivo de catálogo
                fecha_mod_catalogo = datetime.datetime.fromtimestamp(os.path.getmtime("catalogo.csv"))
                st.markdown("### Información del Catálogo")
                st.markdown(f"**Última modificación:** {fecha_mod_catalogo.strftime('%Y-%m-%d %H:%M:%S')}")
                st.markdown(f"**Número de partes:** {len(catalogo['Parte'].unique())}")
                st.markdown(f"**Máquinas:** {', '.join(sorted(catalogo['Maquina'].unique()))}")
            except Exception as e:
                st.error(f"Error al leer información del catálogo: {e}")
        
        st.markdown("---")
        
        if os.path.exists("inventario.json"):
            try:
                # Cargar desde archivo JSON
                with open("inventario.json", "r") as f:
                    datos_inventario = json.load(f)
                
                # Mostrar información de la última actualización
                st.markdown("### Última Actualización del Inventario")
                st.markdown(f"**Fecha:** {datos_inventario.get('ultima_actualizacion', 'Desconocida')}")
                st.markdown(f"**Usuario:** {datos_inventario.get('usuario', 'Sistema')}")
                
                # Mostrar cambios si existen
                if "cambios" in datos_inventario:
                    st.markdown("### Cambios Realizados")
                    for cambio in datos_inventario["cambios"]:
                        st.markdown(f"- {cambio}")
                    
                    # Mostrar detalles expandibles si hay muchos cambios
                    if any("  - " in cambio for cambio in datos_inventario["cambios"]):
                        with st.expander("Ver detalles completos de los cambios"):
                            for cambio in datos_inventario["cambios"]:
                                if "  - " in cambio:
                                    st.markdown(f"{cambio}")
                
                # Mostrar historial de actualizaciones previas (podría implementarse en el futuro)
                st.info("El registro detallado de cambios históricos se implementará en una actualización futura.")
            except Exception as e:
                st.error(f"Error al cargar el registro de cambios: {e}")
        else:
            st.warning("No se ha encontrado registro de cambios. Se creará uno cuando se actualice el inventario.")
    
    # Opción para cerrar sesión de administrador
    if st.button("Cerrar Sesión"):
        st.session_state.is_admin = False
        st.session_state.page = 'dashboard'
        st.rerun()
else:
    # Redirigir a dashboard si hay algún error
    st.session_state.page = 'dashboard'
    st.rerun()
