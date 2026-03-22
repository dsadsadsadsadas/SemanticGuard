@echo off
echo Checking installed Ollama models...
echo.
ollama list
echo.
echo Checking deepseek-r1:latest details...
ollama show deepseek-r1:latest
