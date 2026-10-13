# Fall Detector Project Plan

## Goal

Build a fall detection system for older adults using a camera-based Python detector. The detector is the most important component and must work independently from the web layer.

When a possible fall is detected, the system should wait for a cancellation window. If the alert is not cancelled, it should send a notification through Telegram.

## Current Status

The project already has a first working detector prototype:

- `FirstTests/detector_caidas.py`
- Uses OpenCV, MediaPipe, NumPy, and optional Telegram alerts.
- Detects body posture using pose landmarks.
- Tracks hip descent, fall speed, body aspect ratio, and immobility time.
- Includes a cancellation countdown before sending the alert.
- Sends Telegram messages if token and chat ID are configured.

There is also an earlier prototype:

- `Presentation1/fallDetectionTestingV1.py`

The current best base is `FirstTests/detector_caidas.py`.

## Architecture

The project should be separated into three main parts:

1. Detector Core
2. Alert System
3. Web/API Layer

The detector should not depend directly on the web interface. The web/API should only consume detector events and expose configuration/status.

## Detector Core

Responsibilities:

- Read frames from the camera.
- Detect human pose using MediaPipe.
- Extract relevant body measurements.
- Classify the current state:
- Standing
- Falling
- On the floor
- Alert countdown
- Alert sent
- Avoid false positives when the person sits, bends down, or briefly disappears from frame.
- Emit events when a fall is detected.

Initial detector states:

- `STANDING`
- `FALLING`
- `ON_FLOOR`
- `ALERTING`
- `ALERT_SENT`

Important parameters:

- `CAMERA_INDEX`
- `FALL_SPEED_THRESHOLD`
- `MIN_DESCENT`
- `LYING_ASPECT_RATIO`
- `IMMOBILE_SECONDS`
- `CANCEL_SECONDS`
- `MIN_VISIBILITY`

## Alert System

Responsibilities:

- Receive fall events from the detector.
- Start a cancellation countdown.
- Send alert if not cancelled.
- Support Telegram as the first alert channel.
- Log alert status and errors.

Telegram alert content should include:

- Time of detection.
- Message saying a possible fall was detected.

Secrets should not be hardcoded in the detector code.

Use environment variables:

- `TELEGRAM_TOKEN`
- `TELEGRAM_CHAT_ID`

## Web/API Layer

The web part should be separate from the detector logic.

Possible responsibilities:

- Show detector status.
- Show latest events.
- Configure thresholds.
- Enable/disable Telegram alerts.
- Trigger test alerts.
- Display camera/detector health.
- Eventually support multiple rooms/cameras.

Suggested backend:

- FastAPI

Possible API endpoints:

- `GET /health`
- `GET /status`
- `GET /events`
- `POST /alerts/test`
- `POST /detector/start`
- `POST /detector/stop`
- `GET /config`
- `PUT /config`

The detector should be able to run without the web server.

## Suggested Folder Structure

```text
sip-uade/
  PLAN.md
  README.md
  detector/
    __init__.py
    camera.py
    pose.py
    fall_detector.py
    states.py
    config.py
  alerts/
    __init__.py
    telegram.py
    alert_service.py
  web/
    __init__.py
    main.py
    routes.py
  tests/
    test_fall_detector.py
    test_alert_service.py
  FirstTests/
    detector_caidas.py
    evidencia-prompt-claude.md
    Guia rapida de armado.md
  Presentation1/
    fallDetectionTestingV1.py
    TestLocal1Video.mp4
    Una-caida-puede-cambiar-el-dia.pdf
```

## Implementation Phases

## Phase 1: Clean Detector Prototype

Goal: keep the current detector working, but organize it better.

Tasks:

- Move constants into a config object or config file.
- Separate measurement logic from the main loop.
- Separate state machine logic from camera/display code.
- Keep OpenCV preview for testing.
- Keep Telegram optional.

Deliverable:

- A cleaner detector that still runs locally with `python`.

## Phase 2: Detector Events

Goal: make the detector produce events instead of directly controlling alerts.

Tasks:

- Define event types:
- `person_detected`
- `person_lost`
- `fall_started`
- `person_on_floor`
- `alert_countdown_started`
- `alert_cancelled`
- `alert_confirmed`
- Create a simple event object.
- Make the detector return or publish events.
- Keep console logging for debugging.

Deliverable:

- Detector can run alone and report fall events.

## Phase 3: Telegram Alert Service

Goal: isolate Telegram from the detector.

Tasks:

- Create a Telegram alert module.
- Read token and chat ID from environment variables.
- Add safe error handling.
- Add a test-alert function.
- Avoid crashing detector if Telegram fails.

Deliverable:

- Telegram alerts work independently from detector logic.

## Phase 4: Web/API Backend

Goal: add a web backend that talks to the detector and alert service.

Tasks:

- Create a FastAPI app.
- Add health/status endpoints.
- Add test alert endpoint.
- Add detector status endpoint.
- Add event history endpoint.
- Decide whether the detector runs inside the API process or as a separate process.

Deliverable:

- Local web API can show detector status and send test Telegram alerts.

## Phase 5: Configuration

Goal: make the system configurable without editing code.

Tasks:

- Add `.env` support.
- Add threshold configuration.
- Add camera index configuration.
- Add alert timing configuration.
- Add documentation for each setting.

Deliverable:

- Users can configure the system from environment variables or config file.

## Phase 6: Testing and Validation

Goal: prove that the detector works and identify false positives.

Test cases:

- Real fall forward.
- Real fall backward.
- Real fall sideways.
- Sitting quickly.
- Lying down intentionally.
- Bending down.
- Walking toward camera.
- Walking away from camera.
- Person temporarily leaving frame.
- Poor lighting.
- Partial body visible.

Metrics to record:

- True positives.
- False positives.
- False negatives.
- Detection delay.
- Alert delay.
- Telegram success/failure.

Deliverable:

- A table of test results with tuned thresholds.

## Phase 7: Documentation and Demo

Goal: prepare the project for presentation.

Tasks:

- Write README.
- Explain how detection works.
- Explain how Telegram setup works.
- Add installation instructions.
- Add demo steps.
- Add limitations.
- Add future improvements.

Deliverable:

- Project can be understood, installed, and demonstrated.

## Technical Decisions

Initial decisions:

- Use Python for detector.
- Use OpenCV for camera.
- Use MediaPipe for pose detection.
- Use Telegram Bot API for alerts.
- Use FastAPI for future web/API backend.
- Keep detector independent from web.

Open decisions:

- Should the web API start/stop the detector, or should the detector run as a separate process?
- Should alert events be stored in a file, SQLite database, or only memory at first?
- Should the camera preview be part of the final version or only for testing?
- Should the final deployment run on a laptop, Raspberry Pi, or another device?

## Risks

Main risks:

- False positives when someone sits quickly or lies down intentionally.
- False negatives if the person is partially outside the camera frame.
- MediaPipe may fail in poor lighting.
- Camera angle strongly affects detection quality.
- Telegram requires internet connection.
- Hardcoded thresholds may not work in every room.

Mitigations:

- Tune thresholds using recorded test videos.
- Add cancellation countdown.
- Document recommended camera placement.
- Keep logs for debugging.
- Make thresholds configurable.

## Immediate Next Step

Refactor `FirstTests/detector_caidas.py` into a cleaner detector module while preserving current behavior.

The first implementation should prioritize detector correctness before building the web layer.
