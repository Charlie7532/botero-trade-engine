import json

transcript_path = "/root/.gemini/antigravity-ide/brain/d409e386-fc3c-476f-8e3f-06d084cc241a/.system_generated/logs/transcript.jsonl"
output_path = "/root/botero-trade/Legible_La_Gran_Forencia.md"

with open(transcript_path, 'r') as f:
    lines = f.readlines()

with open(output_path, 'w') as out:
    out.write("# 📖 Cuaderno Recuperado: La Gran Forencia, Base de Datos Inmensa y López de Prado\n\n")
    out.write("> **Nota:** Este es el archivo del hilo GIGANTE (4 MB de memoria cruda) donde molimos los 15,000 créditos, reconstruimos la forencia de las entradas/salidas, y discutimos por qué no debíamos depender del Stop-Loss mecánico de ATR.\n\n---\n\n")
    
    for line in lines:
        try:
            step = json.loads(line)
            source = step.get('source', '')
            step_type = step.get('type', '')
            content = step.get('content', '')
            
            if source == 'USER_EXPLICIT' and 'USER_REQUEST' in content:
                start = content.find('<USER_REQUEST>') + len('<USER_REQUEST>')
                end = content.find('</USER_REQUEST>')
                msg = content[start:end].strip() if end != -1 else content
                out.write(f"### 🧑‍💻 TÚ:\n\n{msg}\n\n---\n\n")
                
            elif source == 'MODEL' and content.strip():
                if step_type in ('PLANNER_RESPONSE', 'MODEL_RESPONSE'):
                    out.write(f"### 🤖 IA:\n\n{content}\n\n---\n\n")
                
        except Exception as e:
            pass

print(f"File created at {output_path}")
