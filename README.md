# Sistema Kanban Transfer Ford (Optimizado)

Aplicación de Streamlit para la planificación de producción de máquinas basada en un archivo CSV. Versión optimizada para mejor rendimiento y usabilidad.

## Funcionalidades

- **Inventario Actual**: Ingrese el inventario actual de cada parte con búsqueda y agrupación por máquina.
- **Dashboard por Máquina**: Visualización de cada máquina con su producto asignado según prioridad.
- **Tabla General**: Tabla completa con todos los cálculos y métricas, con filtros de búsqueda.
- **Panel de Administrador**: Acceso a estadísticas detalladas y sincronización del inventario.
- **Almacenamiento Persistente**: Guarda automáticamente los cambios de inventario.

## Optimizaciones

- **Procesamiento Vectorizado**: Uso de NumPy para cálculos más rápidos.
- **Caché Inteligente**: Reducción de lecturas de archivo con LRU Cache.
- **Interfaz Mejorada**: Búsqueda de partes y agrupación por máquina.
- **Gestión de Memoria**: Optimización de tipos de datos para reducir uso de memoria.
- **Organización Lógica**: Agrupación de pares LH/RH para facilitar la visualización.

## Métricas calculadas

- **Faltante**: Objetivo - Inventario actual
- **Cajas Necesarias**: Faltante ÷ StdPack (redondeado hacia arriba)
- **Tiempo Necesario**: Faltante ÷ Rate (en horas)
- **Prioridad**: Asignada según tiempo necesario (más tiempo = mayor prioridad)

## Ejecución local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar la aplicación
streamlit run app.py
```

## Estructura de archivos

- `app.py`: Aplicación principal de Streamlit (optimizada)
- `catalogo.csv`: Datos de catálogo con partes, máquinas y tasas de producción
- `inventario.json`: Almacenamiento persistente del inventario
- `requirements.txt`: Dependencias del proyecto
- `runtime.txt`: Especificación de la versión de Python

## Acceso Admin

- Usuario: admin
- Contraseña: admin123
