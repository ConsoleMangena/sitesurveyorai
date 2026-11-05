# SiteSurveyor AI — Render Deployment & Integration Guide

Deploy the **SiteSurveyor AI Geospatial Engine** as an independent cloud web service on [Render](https://render.com), then connect it to **`sitesurveyor-framework`** via **MCP SSE** and **REST API**.

---

## 1. Deploying to Render

### Option A: Via GitHub / Blueprint (`render.yaml`)
1. Push `SiteSurveyorAI` to your GitHub / GitLab repository.
2. Log in to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** -> **Blueprint**.
4. Connect your `SiteSurveyorAI` repository. Render automatically reads `render.yaml` and sets up the Docker web service.
5. In the service settings, add your **`DE_AFRICA_TOKEN`** under **Environment Variables**.
6. Render builds the Docker container and assigns you a public URL (e.g. `https://sitesurveyor-engine.onrender.com`).

### Option B: Manual Web Service
1. In Render, select **New +** -> **Web Service**.
2. Connect your repository.
3. Choose **Docker** as the environment (it uses `./Dockerfile`).
4. Set Health Check path to `/health`.
5. Add environment variable: `DE_AFRICA_TOKEN=your_token_here`.
6. Select Plan (**Starter** recommended for multi-spectral raster calculations; 1 GB+ RAM).

---

## 2. Service Endpoints

Once deployed at `https://sitesurveyor-engine.onrender.com`:

| Protocol | Endpoint | Method | Purpose |
| :--- | :--- | :--- | :--- |
| **Health** | `/health` | `GET` | Render healthcheck & active AOI status |
| **Docs** | `/docs` | `GET` | Interactive Swagger UI API documentation |
| **MCP SSE** | `/sse` | `GET` | Server-Sent Events stream for AI agents (OpenClaw, Claude) |
| **MCP Msg** | `/messages/` | `POST` | Message channel for active MCP sessions |
| **REST** | `/api/survey` | `POST` | Full multi-criteria survey across all 4 categories |
| **REST** | `/api/boreholes` | `POST` | Precision borehole siting, groundwater scores & VES advice |
| **REST** | `/api/minerals` | `POST` | Shear-zone gold prospectivity & alteration anomalies |
| **REST** | `/api/soil` | `POST` | Agricultural land capability & erosion risk zoning |
| **REST** | `/api/hazard` | `POST` | Natural hazard exposure & safest buildable locations |
| **REST** | `/api/dossier` | `GET` | Master multi-criteria JSON dossier |
| **Report** | `/api/report` | `GET` | Standalone interactive 18 MB HTML Executive Dossier |
| **Static** | `/outputs/{file}` | `GET` | Direct downloads of `.kmz`, `.geojson`, `.csv`, `.png` |

---

## 3. Connecting to `sitesurveyor-framework`

### 3.1 Via OpenClaw / AI Gateway (`openclaw.config.json`)
In `sitesurveyor-framework/ai-gateway/openclaw.config.json`, add the remote Render MCP service under `"mcp"."servers"`:

```json
{
  "mcp": {
    "servers": {
      "sitesurveyor-db": {
        "command": "node",
        "args": ["./sitesurveyor-mcp/dist/index.js"],
        "cwd": ".",
        "transport": "stdio"
      },
      "sitesurveyor-geospatial": {
        "url": "https://sitesurveyor-engine.onrender.com/sse",
        "transport": "sse"
      }
    }
  }
}
```

The AI Gateway agent immediately inherits all 6 tools (`survey_site`, `get_boreholes`, `get_minerals`, `get_soil_capability`, `get_hazard_safety`, `get_executive_dossier`).

---

### 3.2 Via Supabase Edge Function (`ai-chat` / Deno)
In `sitesurveyor-framework/supabase/functions/_shared/ai-agent.ts`, define a tool that calls the Render REST API:

```typescript
// Add to tool execution switch in ai-agent.ts
if (toolCall.name === "screen_groundwater_boreholes") {
  const { latitude, longitude, top_k = 5 } = toolCall.arguments;
  const res = await fetch("https://sitesurveyor-engine.onrender.com/api/boreholes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ latitude, longitude, top_k }),
  });
  const data = await res.json();
  return JSON.stringify(data);
}
```

---

### 3.3 Embedding Deliverables in the Web UI / CAD Viewer
The frontend (`apps/web`) can:
1. **Download Mobile GPS KMZ**: Link to `https://sitesurveyor-engine.onrender.com/outputs/candidate_borehole_sites.kmz`
2. **Display High-Res Map in Modal**: Image `https://sitesurveyor-engine.onrender.com/outputs/groundwater_potential_map.png`
3. **Open Executive Report**: Render `https://sitesurveyor-engine.onrender.com/api/report` inside an `<iframe>`.
4. **Render Vector Points on Map**: Fetch GeoJSON from `https://sitesurveyor-engine.onrender.com/outputs/candidate_borehole_sites.geojson` and display candidates on Leaflet / Mapbox.

---

## 4. Example REST API Calls

### Groundwater Boreholes Request
```bash
curl -X POST https://sitesurveyor-engine.onrender.com/api/boreholes \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": -19.50487,
    "longitude": 29.84598,
    "top_k": 5
  }'
```

### Full Multi-Criteria Survey Request
```bash
curl -X POST https://sitesurveyor-engine.onrender.com/api/survey \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": -19.50487,
    "longitude": 29.84598,
    "categories": ["all"],
    "client_name": "Thomas Mangena",
    "address": "05 Sekope Highlands, Gweru, Zimbabwe"
  }'
```

