# Hoymiles WiFi Battery Dashboard

Dashboard y scripts para controlar modos de batería de inversores Hoymiles vía WiFi local.

## Estructura
- `hoymiles_wifi/`: Integración custom component para Home Assistant
- `dashboard_control_bateria_wifi.json`: Configuración de la vista Lovelace
- `scripts_wifi.yaml`: Scripts para cada modo de batería

## Modos soportados
1. Autoconsumo
2. Económico
3. Backup
4. Off-Grid
5. Carga Forzada
6. Descarga Forzada
7. Peak Shaving
8. Time of Use (2 periodos)

## Instalación
1. Copiar `hoymiles_wifi/` en `config/custom_components/`
2. Importar la vista desde `dashboard_control_bateria_wifi.json`
3. Importar scripts desde `scripts_wifi.yaml`
4. Configurar la integración vía UI (necesita IP del DTU WiFi)
