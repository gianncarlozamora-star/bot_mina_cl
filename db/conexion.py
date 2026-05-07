import psycopg2
from psycopg2.extras import RealDictCursor
from config import DATABASE_URL

def get_db():
    """Retorna una conexión nueva a PostgreSQL."""
    return psycopg2.connect(DATABASE_URL)

def get_db_dict():
    """Retorna conexión con cursor que devuelve dicts en vez de tuplas."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn, conn.cursor(cursor_factory=RealDictCursor)

def ejecutar(sql, params=None, fetchone=False, fetchall=False):
    """
    Ejecuta una query y retorna resultado.
    Para SELECT usa fetchone=True o fetchall=True.
    Para INSERT/UPDATE/DELETE retorna rowcount.
    """
    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute(sql, params or ())
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
        conn.commit()
        return cur.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def ejecutar_dict(sql, params=None, fetchone=False, fetchall=False):
    """Igual que ejecutar() pero devuelve dicts."""
    conn, cur = get_db_dict()
    try:
        cur.execute(sql, params or ())
        if fetchone:
            return dict(cur.fetchone()) if cur.rowcount != 0 else None
        if fetchall:
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        conn.commit()
        return cur.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
