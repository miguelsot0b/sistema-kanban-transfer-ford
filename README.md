# Sistema Kanban Transfer Ford

Aplicación de Streamlit para la planificación de producción de máquinas basada en un archivo CSV.

## Funcionalidades

- **Inventario Actual**: Ingrese el inventario actual de cada parte en la barra lateral.
- **Dashboard por Máquina**: Visualización de cada máquina con su producto asignado según prioridad.
- **Tabla General**: Tabla completa con todos los cálculos y métricas.

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

- `app.py`: Aplicación principal de Streamlit
- `catalogo.csv`: Datos de catálogo con partes, máquinas y tasas de producción
- `requirements.txt`: Dependencias del proyecto
