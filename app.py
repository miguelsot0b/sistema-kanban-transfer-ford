import streamlit as st
import pandas as pd
import numpy as np
import math
import os
import hashlib
import json
import datetime
from functools import lru_cache

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

# Función para identificar parejas LH/RH (optimizada)
@lru_cache(maxsize=32)
def identificar_parejas(partes_tuple):
    partes = list(partes_tuple)
    parejas = {}
    
    # Enfoque más eficiente para evitar múltiples reemplazos
    for parte in partes:
        lado = None
        base_name = parte
        
        if " LH" in parte:
            lado = "LH"
            base_name = parte.replace(" LH", "")
        elif " RH" in parte:
            lado = "RH"
            base_name = parte.replace(" RH", "")
        
        if lado:  # Solo procesar si es LH o RH
            if base_name not in parejas:
                parejas[base_name] = []
            parejas[base_name].append(parte)
    
    # Filtrar solo los que tienen pares completos (LH y RH)
    pares_completos = {k: v for k, v in parejas.items() if len(v) >= 2}
    return pares_completos

# Calcular métricas (optimizado)
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
    
    # Filtrar para partes con faltante más eficientemente
    mask_faltante = faltante_array > 0
    if mask_faltante.any():
        df_temp = df[mask_faltante].copy()
        
        # Identificar parejas LH/RH - convertir a tuple para cache
        partes_tuple = tuple(df_temp['Parte'].unique())
        parejas = identificar_parejas(partes_tuple)
        
        # Crear una columna para agrupar parejas más eficientemente con un diccionario de mapeo
        parte_a_grupo = {}
        for parte in df_temp['Parte']:
            parte_a_grupo[parte] = parte  # Por defecto, cada parte es su propio grupo
        
        # Poblar el diccionario de mapeo
        for base_name, parts in parejas.items():
            for part in parts:
                parte_a_grupo[part] = base_name
        
        # Aplicar el mapeo directamente
        df_temp['GrupoParte'] = df_temp['Parte'].map(parte_a_grupo)
        
        # Cálculos de tiempo por grupo optimizados
        tiempo_por_grupo = df_temp.groupby(['GrupoParte', 'Maquina'])['TiempoNecesario'].max().reset_index()
        
        # Asignar prioridades de forma vectorizada
        prioridad_por_maquina = {}
        for maquina in tiempo_por_grupo['Maquina'].unique():
            # Filtrar y ordenar en un solo paso
            indices = tiempo_por_grupo.loc[tiempo_por_grupo['Maquina'] == maquina].sort_values('TiempoNecesario', ascending=False).index
            # Asignar prioridades en orden
            for i, idx in enumerate(indices):
                row = tiempo_por_grupo.loc[idx]
                prioridad_por_maquina[(row['GrupoParte'], maquina)] = i + 1
        
        # Asignar prioridades más eficientemente usando vectorización
        tiempo_por_grupo['Prioridad'] = tiempo_por_grupo.apply(
            lambda row: prioridad_por_maquina.get((row['GrupoParte'], row['Maquina']), None), 
            axis=1
        )
        
        # Fusiones más eficientes usando índices
        df_temp = df_temp.merge(
            tiempo_por_grupo[['GrupoParte', 'Maquina', 'Prioridad']], 
            on=['GrupoParte', 'Maquina'], 
            how='left'
        )
        
        # Preparar columnas para el DataFrame principal
        df['GrupoParte'] = df['Parte']  # Inicializar
        
        # Transferir valores calculados de df_temp a df de manera eficiente
        df.loc[mask_faltante, 'Prioridad'] = df_temp['Prioridad'].values
        df.loc[mask_faltante, 'GrupoParte'] = df_temp['GrupoParte'].values
    else:
        df['Prioridad'] = None
        df['GrupoParte'] = df['Parte']
    
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
                partes_grupo = df_faltante[df_faltante['GrupoParte'] == grupo]
                if not partes_grupo.empty:
                    # Guardar prioridad y número de parte más bajo para este grupo
                    prioridades[grupo] = (
                        partes_grupo['Prioridad'].iloc[0],  # Prioridad
                        min(partes_grupo['Parte'].tolist())  # Parte más baja lexicográficamente
                    )
            
            # Ordenar grupos por prioridad primero, luego por número de parte
            grupos_ordenados = sorted(prioridades.items(), key=lambda x: (x[1][0], x[1][1]))
            
            # Tomar el grupo con mayor prioridad (o número de parte más bajo en caso de empate)
            grupo_prioritario = grupos_ordenados[0][0]
            
            # Filtrar las partes de este grupo
            partes_grupo_prioritario = df_faltante[df_faltante['GrupoParte'] == grupo_prioritario]
            
            # Ordenar las partes por nombre para que siempre aparezca primero el número más bajo
            partes_grupo_prioritario = partes_grupo_prioritario.sort_values('Parte')
            
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
                st.markdown(f"**Prioridad:** {int(partes_grupo_prioritario['Prioridad'].iloc[0])}")
                
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
                st.write(f"**Prioridad:** {int(parte_asignada['Prioridad'])}")
            
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
                st.markdown(f"**Prioridad:** {int(siguiente_prioridad)}")
                
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
        
        # Crear input para cada número de parte único
        partes_unicas = sorted(catalogo['Parte'].unique())
        mitad = len(partes_unicas) // 2
        
        # Usar un diseño más eficiente para grandes conjuntos de datos
        # Usar filtro y agrupación para una mejor experiencia de usuario
        search_term = st.text_input("Buscar parte:", key="search_parte")
        
        # Agrupar por máquina para mejor organización
        groupby_machine = st.checkbox("Agrupar por máquina", value=True)
        
        if groupby_machine:
            # Crear un diccionario para mapear partes a máquinas
            parte_a_maquina = {}
            for _, row in catalogo.iterrows():
                parte_a_maquina[row['Parte']] = row['Maquina']
                
            # Agrupar por máquinas
            for maquina in sorted(catalogo['Maquina'].unique()):
                partes_maquina = [p for p in partes_unicas if parte_a_maquina.get(p) == maquina]
                
                # Filtrar por término de búsqueda
                if search_term:
                    partes_maquina = [p for p in partes_maquina if search_term.lower() in p.lower()]
                
                # Si hay partes para esta máquina después del filtrado
                if partes_maquina:
                    with st.expander(f"{maquina} ({len(partes_maquina)} partes)"):
                        # Crear columnas dentro del expander
                        mc1, mc2 = st.columns(2)
                        mitad_maquina = len(partes_maquina) // 2
                        
                        # Primera columna de la máquina
                        with mc1:
                            for parte in partes_maquina[:mitad_maquina]:
                                st.session_state.temp_inventario[parte] = st.number_input(
                                    f"{parte}", 
                                    min_value=0, 
                                    value=st.session_state.inventario[parte],
                                    key=f"inv_{parte}"
                                )
                        
                        # Segunda columna de la máquina
                        with mc2:
                            for parte in partes_maquina[mitad_maquina:]:
                                st.session_state.temp_inventario[parte] = st.number_input(
                                    f"{parte}", 
                                    min_value=0, 
                                    value=st.session_state.inventario[parte],
                                    key=f"inv2_{parte}"
                                )
        else:
            # Modo tradicional en dos columnas
            # Filtrar por término de búsqueda
            if search_term:
                partes_filtradas = [p for p in partes_unicas if search_term.lower() in p.lower()]
            else:
                partes_filtradas = partes_unicas
                
            mitad = len(partes_filtradas) // 2
            
            # Primera columna
            with col1:
                for parte in partes_filtradas[:mitad]:
                    st.session_state.temp_inventario[parte] = st.number_input(
                        f"{parte}", 
                        min_value=0, 
                        value=st.session_state.inventario[parte],
                        key=f"inv_{parte}"
                    )
            
            # Segunda columna
            with col2:
                for parte in partes_filtradas[mitad:]:
                    st.session_state.temp_inventario[parte] = st.number_input(
                        f"{parte}", 
                        min_value=0, 
                        value=st.session_state.inventario[parte],
                        key=f"inv2_{parte}"
                    )
        
        # Campos para registrar usuario que realiza el cambio
        usuario = st.text_input("Su Nombre (para registro de cambios)", key="nombre_usuario")
        
        # Botón para guardar cambios
        submitted = st.form_submit_button("Guardar Cambios")
        
        if submitted:
            if not usuario.strip():
                st.warning("Por favor ingrese su nombre para registrar el cambio")
            else:
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
    
    # Crear pestañas para diferentes secciones del panel de administrador
    tab1, tab2 = st.tabs(["📋 Tabla General", "📝 Registro de Cambios"])
    
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
    orden = ['Maquina', 'Prioridad', 'GrupoParte']
    df_tabla = df_tabla.sort_values(orden, na_position='last')
    df_tabla = df_tabla.fillna({'Prioridad': '-'})
    
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
        
        # Agrupar por GrupoParte y Máquina
        df_grouped = df_para_agrupar.groupby(['GrupoParte', 'Maquina']).agg({
            'Inventario': 'mean',
            'Objetivo': 'mean',
            'Faltante': 'sum',
            'CajasNecesarias': 'sum',
            'TiempoNecesario': 'max',
            'Prioridad': 'min'
        }).reset_index()
        
        # Formatear columnas numéricas
        df_grouped['Inventario'] = df_grouped['Inventario'].astype(int)
        df_grouped['Objetivo'] = df_grouped['Objetivo'].astype(int)
        df_grouped['Faltante'] = df_grouped['Faltante'].astype(int)
        df_grouped['CajasNecesarias'] = df_grouped['CajasNecesarias'].astype(int)
        df_grouped['TiempoNecesario'] = df_grouped['TiempoNecesario'].round(2)
        
        # Ordenar por máquina y prioridad
        df_grouped = df_grouped.sort_values(['Maquina', 'Prioridad'], na_position='last')
        df_grouped = df_grouped.fillna({'Prioridad': '-'})
        
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
                    # Ordenar por prioridad
                    df_maquina_grupos = df_maquina_grupos.sort_values('Prioridad')
                    
                    st.write(f"### Máquina: {maquina}")
                    
                    # Crear lista ordenada con los grupos y sus métricas principales
                    for i, (_, grupo) in enumerate(df_maquina_grupos.iterrows()):
                        if pd.notna(grupo['Prioridad']) and grupo['Prioridad'] != '-':
                            st.write(f"**{i+1}. {grupo['GrupoParte']}** - Prioridad: {int(grupo['Prioridad'])} - Tiempo: {grupo['TiempoNecesario']:.2f} horas - Cajas: {int(grupo['CajasNecesarias'])}")
                    
                    st.divider()
    
    # Información sobre el último cálculo
    st.caption("La prioridad se calcula según el tiempo necesario para alcanzar el objetivo.")
    
    with tab2:
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
