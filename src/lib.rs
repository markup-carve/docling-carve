use carve::api::{self, Carve, Options, WriteOptions};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

// carve-rs next2 still carries the 0.1 crate version, so the Carve language version is stated here.
const ENGINE_VERSION: &str = "0.2";

fn value_error(error: api::Error) -> PyErr {
    PyValueError::new_err(error.to_string())
}

/// The canonical Carve source of an AST 2.0 tree given as JSON (`decodeTree`, then `write`).
#[pyfunction]
fn render_ast_json(source: &str) -> PyResult<String> {
    let tree = api::decode_tree(source).map_err(value_error)?;
    Carve::new()
        .write(&tree, &WriteOptions::default())
        .map_err(value_error)
}

/// The AST 2.0 tree of a Carve source, encoded as JSON (`parse`, then `encodeTree`).
#[pyfunction]
fn parse_json(source: &str) -> PyResult<String> {
    let tree = api::parse(source, &Options::default()).map_err(value_error)?;
    Ok(api::encode_tree(&tree))
}

#[pyfunction]
fn to_html(source: &str) -> PyResult<String> {
    api::render(source, &Options::default()).map_err(value_error)
}

/// The canonical spelling of a Carve source (`format`).
#[pyfunction]
fn to_carve(source: &str) -> PyResult<String> {
    Carve::new()
        .format(source, &WriteOptions::default())
        .map_err(value_error)
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("ENGINE_VERSION", ENGINE_VERSION)?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(render_ast_json, m)?)?;
    m.add_function(wrap_pyfunction!(parse_json, m)?)?;
    m.add_function(wrap_pyfunction!(to_html, m)?)?;
    m.add_function(wrap_pyfunction!(to_carve, m)?)?;
    Ok(())
}
