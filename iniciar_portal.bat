@echo off
title Portal WhatsApp - Circulo Medico de Salta
echo ============================================================
echo   Iniciando Portal Web de WhatsApp - Circulo Medico
echo ============================================================
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe iniciar_portal.py
) else (
    python iniciar_portal.py
)
pause
