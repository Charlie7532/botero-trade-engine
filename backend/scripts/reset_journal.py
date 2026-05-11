import os
import sys
import psycopg2
from dotenv import load_dotenv

def reset_journal():
    load_dotenv()
    db_url = os.getenv("POSTGRES_URL")
    
    if not db_url:
        print("❌ POSTGRES_URL no encontrado en el entorno.")
        sys.exit(1)
        
    try:
        print("🔌 Conectando a Neon PostgreSQL...")
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Las tablas usan CASCADE para asegurar que cualquier clave foránea también se respete
        tables = [
            "engine.trade_patterns",
            "engine.trade_snapshots",
            "engine.trade_journal"
        ]
        
        for table in tables:
            print(f"🧹 Truncando {table}...")
            # El bloque try/except es por si la tabla no existe aún en este entorno
            try:
                cursor.execute(f"TRUNCATE TABLE {table} CASCADE;")
                print(f"✅ {table} vaciada correctamente.")
            except psycopg2.errors.UndefinedTable:
                print(f"⚠️ {table} no existe, se omitió.")
                
        cursor.close()
        conn.close()
        print("🚀 Memory Guard reseteado. Listo para aprender la nueva estructura de 13D.")
        
    except Exception as e:
        print(f"❌ Error durante el reseteo: {e}")

if __name__ == "__main__":
    reset_journal()
