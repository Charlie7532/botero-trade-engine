import sys
import json
from pathlib import Path

def convert_to_md(jsonl_path):
    path = Path(jsonl_path)
    if not path.exists():
        print(f"Error: No se encontró el archivo {jsonl_path}")
        return

    output_path = path.parent.parent.parent / f"Legible_{path.parent.parent.parent.name[:8]}.md"
    
    with open(path, 'r', encoding='utf-8') as f_in, open(output_path, 'w', encoding='utf-8') as f_out:
        f_out.write(f"# 📝 Transcripción Legible\n")
        f_out.write(f"**Archivo de Origen:** `{path}`\n\n---\n\n")
        
        for line in f_in:
            if not line.strip(): continue
            try:
                data = json.loads(line)
                source = data.get("source", "UNKNOWN")
                content = data.get("content", "")
                created_at = data.get("created_at", "")
                
                # Omitir pasos internos ruidosos o llamadas de herramientas que no son texto
                if not content: continue
                if source == "SYSTEM" and not "content" in data: continue
                
                if source == "USER_EXPLICIT":
                    f_out.write(f"### 👤 Usuario ({created_at})\n")
                elif source == "MODEL":
                    f_out.write(f"### 🤖 IA ({created_at})\n")
                else:
                    f_out.write(f"### ⚙️ {source} ({created_at})\n")
                    
                f_out.write(f"{content}\n\n---\n\n")
            except Exception as e:
                pass

    print(f"✅ ¡Éxito! Archivo legible creado en:\n{output_path.absolute()}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python convert.py <ruta_al_transcript.jsonl>")
    else:
        convert_to_md(sys.argv[1])
