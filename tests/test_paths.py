"""Rutas de recursos incluidos y de datos del usuario (app instalada con recursos de solo lectura)."""

from flightcase import paths


def test_datos_del_usuario_aparte_de_los_recursos(tmp_path, monkeypatch):
    monkeypatch.setenv("FLIGHTCASE_DATA_DIR", str(tmp_path))
    assert paths.user_data_dir() == tmp_path
    assert paths.user_resource("taller_estilos_propios.json").parent == tmp_path
    for nombre in ("catalogo_fr.json", "taller_parametros.json", "taller_estilos.json", "icono.png"):
        assert paths.bundled_resource(nombre).is_file()
