# HTTP and MCP clients

Install the `http` extra and run `docling-carve serve`. The default bind address is `127.0.0.1`. Set `DOCLING_CARVE_TOKEN` before exposing the service to other clients. `/health` is public; conversion, extraction, capabilities, and schema routes require the configured token.

`POST /v1/convert` accepts `{"document": <Docling JSON>, "options": {...}}`. The response follows the report schema and includes base64 image assets. Options match the exporter except filesystem paths are unavailable. Unknown request fields are refused.

```javascript
const response = await fetch('http://127.0.0.1:8080/v1/convert', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`},
  body: JSON.stringify({document, options: {strict: true}})
});
if (!response.ok) throw new Error(await response.text());
const report = await response.json();
console.log(report.value);
```

```php
$curl = curl_init('http://127.0.0.1:8080/v1/convert');
curl_setopt_array($curl, [
    CURLOPT_POST => true,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'Authorization: Bearer ' . $token],
    CURLOPT_POSTFIELDS => json_encode(['document' => $document, 'options' => ['strict' => true]], JSON_THROW_ON_ERROR),
]);
$body = curl_exec($curl);
if ($body === false || curl_getinfo($curl, CURLINFO_RESPONSE_CODE) !== 200) {
    throw new RuntimeException($body === false ? curl_error($curl) : $body);
}
$report = json_decode($body, true, 512, JSON_THROW_ON_ERROR);
echo $report['value'];
curl_close($curl);
```

`POST /v1/extract?filename=report.pdf&pdf_pipeline=native` accepts raw file bytes. Install `extract` as well. Query options include `strict`, `ocr`, and `max_pages`. The body limit defaults to 16000000 bytes and applies while streaming, including requests without `Content-Length`.

HTTP errors use 400 for invalid input, 401 for authentication, 413 for body limits, 422 for strict refusal, and 503 when extraction dependencies are missing. Strict refusal includes the report in `detail.report`. `GET /v1/capabilities` reports installed interfaces; `GET /v1/schema` returns the report schema. FastAPI serves the OpenAPI document at `/openapi.json`.

## MCP

Install `mcp` and configure a stdio client:

```json
{
  "mcpServers": {
    "docling-carve": {
      "command": "docling-carve",
      "args": ["mcp", "--root", "/absolute/path/to/incoming"]
    }
  }
}
```

Tools are `docling_to_carve`, `docling_carve_capabilities`, and `docling_extract`. Strict refusal returns `is_error` with the report in structured content and text. The schema resource is `docling-carve://schema/report-v1`. JSON conversion has a 16000000-byte limit. Extraction requires a configured root and refuses paths, including resolved symlinks, outside it. Without `--root`, JSON conversion remains available.

## Container

```sh
docker build -t docling-carve .
docker run --rm -p 127.0.0.1:8080:8080 -e DOCLING_CARVE_TOKEN docling-carve
```

The default image includes HTTP and MCP, and runs as an unprivileged user. Set build argument `EXTRAS=http,mcp,extract` for extraction. The extraction extra installs Docling's platform dependencies and can substantially increase image size; model downloads still occur at runtime for the standard PDF pipeline.
