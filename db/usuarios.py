from db.conexion import ejecutar, ejecutar_dict
from config import hora_peru

def obtener_usuario(telefono: str) -> dict | None:
    """Retorna datos del usuario por teléfono o None si no existe."""
    row = ejecutar(
        """SELECT u.id, u.nombre, u.rol, u.empresa_id, u.maquina_id, u.activo,
                  e.codigo AS empresa, m.codigo AS maquina, m.sufijo_tarifa
           FROM usuarios_bot u
           LEFT JOIN cat_empresas e ON u.empresa_id = e.id
           LEFT JOIN cat_maquinas m ON u.maquina_id = m.id
           WHERE u.telefono = %s AND u.activo = TRUE""",
        (telefono,), fetchone=True
    )
    if not row:
        return None
    return {
        "id":       row[0],
        "nombre":   row[1],
        "rol":      row[2],
        "empresa_id": row[3],
        "maquina_id": row[4],
        "activo":   row[5],
        "empresa":  row[6],
        "maquina":  row[7],
        "sufijo_tarifa": row[8],
    }

def registrar_usuario(telefono: str, nombre: str, rol: str,
                       empresa_id: int = None, maquina_id: int = None) -> int:
    """Inserta un nuevo usuario y retorna su id."""
    row = ejecutar(
        """INSERT INTO usuarios_bot (telefono, nombre, rol, empresa_id, maquina_id)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (telefono) DO UPDATE
               SET nombre=EXCLUDED.nombre, activo=TRUE
           RETURNING id""",
        (telefono, nombre, rol, empresa_id, maquina_id), fetchone=True
    )
    return row[0] if row else None

def actualizar_ultimo_acceso(usuario_id: int):
    ejecutar(
        "UPDATE usuarios_bot SET ultimo_acceso=%s WHERE id=%s",
        (hora_peru(), usuario_id)
    )

def obtener_maquinas_activas() -> list:
    """Lista de máquinas activas con su empresa para mostrar en menú."""
    rows = ejecutar(
        """SELECT m.id, m.codigo, e.codigo AS empresa
           FROM cat_maquinas m
           JOIN cat_empresas e ON m.empresa_id = e.id
           WHERE m.activo = TRUE
           ORDER BY e.codigo, m.codigo""",
        fetchall=True
    )
    return [{"id": r[0], "codigo": r[1], "empresa": r[2]} for r in rows]

def obtener_empresas_activas() -> list:
    rows = ejecutar(
        "SELECT id, codigo, nombre FROM cat_empresas WHERE tipo='CONTRATISTA' ORDER BY codigo",
        fetchall=True
    )
    return [{"id": r[0], "codigo": r[1], "nombre": r[2]} for r in rows]
