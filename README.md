# test-server (LiveKit Agents) - Delivery Voice Assistant

Ce projet est un serveur **LiveKit Agents** qui fait tourner un assistant vocal (nomme "RYTLE") pour des livreurs.
Il se connecte a une room LiveKit, recoit des evenements depuis une app Flutter via le **Data Channel**, et applique un workflow deterministe de "delivery treatment" grace a une **machine a etats (FSM)**.

L'objectif principal: quand on est dans le workflow de livraison, l'agent **ne doit pas improviser**. Il doit repeter la question tant que la reponse n'est pas conforme (oui/non, numero, etc.).

---

## Prerequis

- Python >= 3.12
- `uv` (package manager)
- Un projet/serveur LiveKit (Cloud ou self-hosted)
- Des cles API pour STT/LLM/TTS (voir ci-dessous)

---

## Configuration (.env.local)

Le serveur charge `.env.local` au demarrage (voir `agent.py`).

Variables attendues:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `OPENAI_API_KEY` (LLM: `openai/gpt-4o-mini`)
- `ASSEMBLYAI_API_KEY` (STT: `assemblyai/universal-streaming:en`)
- `CARTESIA_API_KEY` (TTS: `cartesia/...`)

Notes:

- Ne committez jamais de vraies cles API.
- `NEXT_PUBLIC_LIVEKIT_URL` peut etre utile cote client, mais n'est pas obligatoire cote serveur.

---

## Lancer le serveur

Installer les dependances:

```powershell
uv sync
```

Mode console (pratique pour debug):

```powershell
uv run agent.py console --text
```

Mode worker (connexion a LiveKit, en attente de jobs):

```powershell
uv run agent.py start
```

Aide CLI (liste des commandes LiveKit Agents):

```powershell
uv run agent.py --help
```

---

## Configuration LiveKit (livekit.toml)

Le fichier `livekit.toml` peut contenir des infos "projet" (subdomain) et "agent id" pour LiveKit Cloud.
Si vous n'utilisez pas ces features, vous pouvez vous contenter des variables d'environnement `LIVEKIT_*`.

---

## Architecture (vue d'ensemble)

### 1) Point d'entree

- `agent.py`:
  - Cree `AgentServer()`
  - Declare une session RTC via `@server.rtc_session()`
  - Demarre une `AgentSession` (STT/LLM/TTS + VAD)
  - Gere les evenements Data Channel recus depuis Flutter
  - Maintient un `AgentState` minimal: `AgentMode.NORMAL` ou `AgentMode.DELIVERY_TREATMENT`

### 2) FSM generique

- `agent_helper/core.py`: moteur FSM async (transitions, guard, action, verrou async)
- `agent_helper/transition.py`: dataclass `Transition`
- `agent_helper/enums.py`: enums `Event`, `TreatmentState`, `AgentMode`, ...

### 3) FSM "delivery treatment"

- `delivery_treatment.py`:
  - Defini les actions (TTS + publish event) dans `TreatmentActions`
  - Defini les guards (regles metier) dans `TreatmentGuards`
  - Construit les transitions dans `build_treatment_transitions()`
  - Fournit un wrapper haut niveau `DeliveryTreatmentFSM`
  - Fournit `reprompt()` pour reposer la question courante

### 4) Regles metier livraison

- `delivery.py`:
  - `FailureReason` (1..6) + mapping texte
  - `DeliveryRules` (photo requise, detail requis, etc.)
  - `DeliveryContext` (etat de la livraison en cours)

### 5) Donnees "Trips" (en memoire)

- `data/models/trip_store.py`: store singleton (in-memory)
- `data/models/trip_listener.py`: recoit des updates trips (dict Flutter) et notifie des callbacks
- `data/models/Trip.py`, `data/models/trip_state.py`: modele Trip et etats

---

## Mode NORMAL vs DELIVERY_TREATMENT

### Mode NORMAL

En `AgentMode.NORMAL`, le LLM repond normalement et peut appeler des tools (voir `tools.py`).

### Mode DELIVERY_TREATMENT

En `AgentMode.DELIVERY_TREATMENT`, l'assistant "prend la main" et:

- Parse la phrase utilisateur (yes/no, numero, texte)
- Envoie l'event au `DeliveryTreatmentFSM`
- Si la reponse n'est pas valide pour l'etat courant: **reprompt** (boucle) et ne laisse pas le LLM divaguer

Le controle du "bouclage" est fait dans `Assistant.on_user_turn_completed()` (voir `agent.py`).

---

## Workflow "delivery treatment"

Declenchement:

- Flutter envoie un event Data Channel `destination_arrival` (ou `arrived`).
- Le serveur:
  - `state.mode = AgentMode.DELIVERY_TREATMENT`
  - `delivery_fsm.start_treatment(trip_id, address)`
  - Pose la question: "Is the delivery completed? yes/no"

Etats (voir `agent_helper/enums.py`):

- `ASK_DELIVERY_COMPLETION` -> attend YES/NO
- `ASK_NON_DELIVERY_REASON` -> attend un numero 1..6
- `ASK_REASON_DETAIL` -> attend un texte (cas "6")
- `ASK_PHOTO` -> attend un event Flutter `photo_taken` ou `photo_not_taken` (le vocal repete juste la consigne)
- `FINALIZE` -> publie `delivery_treatment_finished`

---

## Protocole Data Channel (Flutter <-> serveur)

Tous les messages sont des JSON (bytes) envoyes sur le Data Channel de la room LiveKit.

### Flutter -> serveur

- Update d'un trip:
```json
{ "type": "trip_update", "data": { "id": "...", "address": "...", "state": "inProgress", "location": {...} } }
```

- Arrivee a destination (demarre le workflow):
```json
{ "type": "destination_arrival", "trip_id": "trip-123", "address": "..." }
```
Le serveur accepte aussi `type: "arrived"` et les alias d'id `id` / `delivery_id`.

- Resultat photo:
```json
{ "type": "photo_taken", "trip_id": "trip-123" }
{ "type": "photo_not_taken", "trip_id": "trip-123" }
```

### Serveur -> Flutter

- Demande photo (ouvrir camera cote app):
```json
{ "type": "ask_photo_event", "delivery_id": "trip-123", "address": "...", "timestamp": "..." }
```

- Trip complete / cancelled (publie par `agent.py`):
```json
{ "type": "trip_completed_event", "trip_id": "trip-123", "timestamp": "..." }
{ "type": "trip_cancelled_event", "trip_id": "trip-123", "reason": "...", "timestamp": "..." }
```

- Fin de traitement (publie par `DeliveryTreatmentFSM`):
```json
{ "type": "delivery_treatment_finished", "delivery_id": "trip-123", "success": true, "final_state": "COMPLETED", "timestamp": "..." }
```

---

## Les endroits ou modifier facilement

- Prompts (phrases TTS du workflow): `delivery_treatment.py` -> `TreatmentActions`
- Parsing oui/non: `agent.py` -> `POSITIVE_RE`, `NEGATIVE_RE`
- Extraction numero (1..6): `agent.py` -> `extract_number()`
- Regles photo/detail: `delivery.py` -> `DeliveryRules`
- Transitions FSM: `delivery_treatment.py` -> `build_treatment_transitions()`
- Tools LLM (mode normal): `tools.py` + liste `tools=[...]` dans `agent.py`

---

## Notes importantes / gotchas

- `TripStore` est **en memoire**: un restart du serveur vide tout.
- En console audio sur Windows, le mode toggle clavier peut etre bruyant: prefere `uv run agent.py console --text` pour debugger.
- Les secrets dans `.env.local` doivent rester locaux.

---

## Docker (optionnel)

Un `Dockerfile` est fourni (base `uv`) et lance par defaut:

```text
uv run agent.py start
```

