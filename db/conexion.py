import pg8000
import urllib.parse
from config import DATABASE_URL

def _parse(url):
    r = urllib.parse.urlparse(url)
    return dict(host=r.hostname, port=r.port or 5432,
                user=r.username, password=r.password,
                database=r.path.lstrip("/"), ssl_context=True)

def get_db():
    return pg8000.connect(**_parse(DATABASE_URL))

def ejecutar(sql, params=None, fetchone=False, fetchall=False):
    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute(sql, params or ())
        if fetchone:
            result = cur.fetchone()
            conn.commit()
            return result
        if fetchall:
            result = cur.fetchall()
            conn.commit()
            return result
        conn.commit()
        return cur.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def ejecutar_dict(sql, params=None, fetchone=False, fetchall=False):
    conn = get_db()
    cur  = conn.cursor()
    try:
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description] if cur.description else []
        if fetchone:
            row = cur.fetchone()
            conn.commit()
            return dict(zip(cols, row)) if row else None
        if fetchall:
            rows = cur.fetchall()
            conn.commit()
            return [dict(zip(cols, r)) for r in rows]
        conn.commit()
        return cur.rowcount
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
