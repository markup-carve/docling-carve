use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn render_ast_json(source: &str) -> PyResult<String> {
    let doc = carve_rs::from_json(source).map_err(|e| PyValueError::new_err(e.to_string()))?;
    carve_rs::render_carve(&doc).map_err(|e| PyValueError::new_err(e.to_string()))
}

#[pyfunction]
fn parse_json(source: &str) -> String {
    carve_rs::to_json_with_options(source, &carve_rs::Options::default())
}

#[pyfunction]
fn to_html(source: &str) -> String {
    carve_rs::to_html(source)
}

#[pyfunction]
fn to_carve(source: &str) -> String {
    carve_rs::to_carve(source)
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("ENGINE_VERSION", "0.1.7")?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(render_ast_json, m)?)?;
    m.add_function(wrap_pyfunction!(parse_json, m)?)?;
    m.add_function(wrap_pyfunction!(to_html, m)?)?;
    m.add_function(wrap_pyfunction!(to_carve, m)?)?;
    Ok(())
}
