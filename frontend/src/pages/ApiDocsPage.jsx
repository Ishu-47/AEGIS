import { useApp } from "../App";
import { Copy, Check } from "lucide-react";
import { useState } from "react";

function CodeBlock({ title, language, code }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-xl border border-ink/8 overflow-hidden">
      <div className="flex items-center justify-between bg-ink/5 px-4 py-2">
        <span className="text-xs font-medium text-ink/60">{title}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-xs text-ink/40 transition hover:text-ink"
        >
          {copied ? (
            <><Check size={12} /> Copied</>
          ) : (
            <><Copy size={12} /> Copy</>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto bg-ink/[0.03] px-4 py-3 font-mono text-xs leading-6 text-ink/80">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export default function ApiDocsPage() {
  const { selected } = useApp();
  const appId = selected?.id || "<application-id>";
  const apiKey = selected?.api_key || "<your-api-key>";

  const curlIngest = `curl -X POST http://localhost:8000/api/ingest/logs \\
  -H "Content-Type: application/json" \\
  -H "X-API-Key: ${apiKey}" \\
  -d '{
    "application_id": "${appId}",
    "events": [
      {
        "timestamp": "2026-10-25T10:21:30Z",
        "severity": "ERROR",
        "service": "PaymentService",
        "message": "Payment processing timeout after 30s",
        "correlation_id": "req-abc-123"
      },
      {
        "timestamp": "2026-10-25T10:21:31Z",
        "severity": "ERROR",
        "service": "OrderService",
        "message": "Failed to complete order due to payment failure",
        "correlation_id": "req-abc-123"
      }
    ]
  }'`;

  const pythonExample = `import requests

API_URL = "http://localhost:8000/api/ingest/logs"
API_KEY = "${apiKey}"
APP_ID = "${appId}"

response = requests.post(
    API_URL,
    headers={"X-API-Key": API_KEY},
    json={
        "application_id": APP_ID,
        "events": [
            {
                "timestamp": "2026-10-25T10:21:30Z",
                "severity": "ERROR",
                "service": "MyService",
                "message": "Connection refused to database",
                "correlation_id": "trace-456",
            }
        ],
    },
)

print(response.json())`;

  const nodeExample = `const response = await fetch(
  "http://localhost:8000/api/ingest/logs",
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": "${apiKey}",
    },
    body: JSON.stringify({
      application_id: "${appId}",
      events: [
        {
          timestamp: new Date().toISOString(),
          severity: "ERROR",
          service: "ExpressApp",
          message: "Unhandled rejection: TypeError",
          correlation_id: "req-789",
        },
      ],
    }),
  }
);

console.log(await response.json());`;

  const javaExample = `HttpClient client = HttpClient.newHttpClient();

String body = """
{
  "application_id": "${appId}",
  "events": [{
    "timestamp": "2026-10-25T10:21:30Z",
    "severity": "ERROR",
    "service": "SpringApp",
    "message": "NullPointerException in UserController",
    "correlation_id": "trace-001"
  }]
}
""";

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://localhost:8000/api/ingest/logs"))
    .header("Content-Type", "application/json")
    .header("X-API-Key", "${apiKey}")
    .POST(HttpRequest.BodyPublishers.ofString(body))
    .build();

HttpResponse<String> response = client.send(
    request, HttpResponse.BodyHandlers.ofString()
);`;

  return (
    <div className="space-y-8 animate-fade-in">
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-oxblood">
          Integration
        </p>
        <h2 className="mt-2 text-xl font-semibold">Ingestion API</h2>
        <p className="mt-1 text-sm text-ink/55">
          Send diagnostic events from any application using standard HTTP
          requests.
        </p>
      </div>

      {/* Schema documentation */}
      <div className="rounded-2xl border border-ink/8 bg-white/40 p-6">
        <h3 className="font-semibold">Event Schema</h3>
        <p className="mt-2 text-sm text-ink/60">
          Each event in the <code className="rounded bg-ink/5 px-1.5 py-0.5 font-mono text-xs">events</code> array
          accepts these fields:
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink/8 text-left">
                <th className="pb-2 pr-4 font-semibold">Field</th>
                <th className="pb-2 pr-4 font-semibold">Type</th>
                <th className="pb-2 pr-4 font-semibold">Required</th>
                <th className="pb-2 font-semibold">Description</th>
              </tr>
            </thead>
            <tbody className="text-ink/70">
              {[
                ["message", "string", "Yes", "The log message, error text, or stack trace."],
                ["severity", "string", "No", "DEBUG, INFO, WARN, ERROR, CRITICAL, FATAL. Defaults to INFO."],
                ["service", "string", "No", "Name of the service or component. Defaults to 'unknown'."],
                ["timestamp", "string", "No", "ISO 8601 timestamp. Defaults to current UTC time."],
                ["correlation_id", "string", "No", "Trace or request ID for linking related events."],
                ["raw_event", "object", "No", "Arbitrary metadata to store alongside the event."],
              ].map(([field, type, req, desc]) => (
                <tr key={field} className="border-b border-ink/5">
                  <td className="py-2.5 pr-4 font-mono text-xs font-medium text-oxblood">{field}</td>
                  <td className="py-2.5 pr-4 font-mono text-xs">{type}</td>
                  <td className="py-2.5 pr-4">{req}</td>
                  <td className="py-2.5 text-xs">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Endpoint info */}
      <div className="rounded-2xl border border-ink/8 bg-white/40 p-6 space-y-3">
        <h3 className="font-semibold">Endpoint</h3>
        <div className="flex items-center gap-2">
          <span className="rounded bg-oxblood/10 px-2.5 py-1 text-xs font-bold text-oxblood">
            POST
          </span>
          <code className="font-mono text-sm">/api/ingest/logs</code>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded bg-ink/8 px-2.5 py-1 text-xs font-bold text-ink/60">
            Header
          </span>
          <code className="font-mono text-sm">X-API-Key: {`{api_key}`}</code>
        </div>
        <p className="text-xs text-ink/50">
          Maximum 500 events per request. Investigation is not triggered
          automatically — call the investigate endpoint separately.
        </p>
      </div>

      {/* Code examples */}
      <div className="space-y-4">
        <h3 className="font-semibold">Integration examples</h3>
        <CodeBlock title="cURL" language="bash" code={curlIngest} />
        <CodeBlock title="Python (requests)" language="python" code={pythonExample} />
        <CodeBlock title="Node.js (fetch)" language="javascript" code={nodeExample} />
        <CodeBlock title="Java (HttpClient)" language="java" code={javaExample} />
      </div>

      {!selected && (
        <div className="rounded-xl border border-oxblood/20 bg-oxblood/5 p-4 text-sm text-ink/60">
          Register an application to see your actual API key and application
          ID in the examples above.
        </div>
      )}
    </div>
  );
}
