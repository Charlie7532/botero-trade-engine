"""
Migration: Saneamiento de duplicados horocíclicos en market.ohlcv_bars
y actualización de metadata corporativa para tickers delistados/rebrandeados.
"""
from backend.modules.shared.infrastructure.timescale_data_store import TimescaleDataStore

def run():
    store = TimescaleDataStore()
    conn = store._conn()
    try:
        with conn.cursor() as cur:
            # 1. Eliminar barras de 1d que no sean medianoche UTC en los 4 tickers afectados
            print("1. Eliminando barras con hora distinta a 00:00:00 UTC...")
            cur.execute("""
                DELETE FROM market.ohlcv_bars
                WHERE timeframe = '1d'
                  AND (EXTRACT(HOUR FROM time) != 0 OR EXTRACT(MINUTE FROM time) != 0)
                  AND ticker IN ('TNX', 'IRX', 'DXY', 'VIX');
            """)
            print(f"   Filas duplicadas eliminadas: {cur.rowcount}")

            # 2. Actualizar update_source a 'none_historical_only' para tickers delistados/privatizados
            retired_tickers = ['CTRA', 'EA', 'AVB', 'EQR', 'CPI']
            print(f"2. Actualizando metadata de tickers retirados {retired_tickers} a 'none_historical_only'...")
            for tk in retired_tickers:
                cur.execute("""
                    UPDATE market.ticker_metadata
                    SET update_source = 'none_historical_only',
                        updated_at = NOW()
                    WHERE ticker = %s;
                """, (tk,))
                print(f"   {tk}: status updated ({cur.rowcount} row)")

            # 3. Registrar VMRK (fusión AVB + EQR) como ticker activo en ticker_metadata
            print("3. Registrando VMRK (Vivmark Residential) en ticker_metadata...")
            cur.execute("""
                INSERT INTO market.ticker_metadata (ticker, sector, industry, asset_type, update_source, updated_at)
                VALUES ('VMRK', 'Real Estate', 'REIT - Residential', 'STOCK', 'vault_ohlcv_bars', NOW())
                ON CONFLICT (ticker) DO UPDATE
                SET update_source = 'vault_ohlcv_bars',
                    sector = 'Real Estate',
                    industry = 'REIT - Residential',
                    updated_at = NOW();
            """)
            print("   VMRK registrado con éxito.")

        conn.commit()
        print("\nTransacción confirmada en Neon Vault.")
    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
        raise
    finally:
        store._put(conn)
        store.close()

if __name__ == "__main__":
    run()
