"""Run real HTTP checks with all non-loopback Python connections forbidden."""

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import requests
import uvicorn

blocked = []


def enforce_offline(event, args):
    if event == "socket.connect":
        address = args[1]
        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "::1"):
            blocked.append(event)
            raise RuntimeError("Non-loopback connection forbidden by offline API check")
    elif event == "socket.getaddrinfo" and args[0] not in ("127.0.0.1", "::1", "localhost"):
        blocked.append(event)
        raise RuntimeError("External DNS forbidden by offline API check")


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.addaudithook(enforce_offline)
os.environ.pop("MINGLI_API_KEY", None)
from api.server import app, service
from runtime.user_memory import UserMemory

birth = {"year": 1990, "month": 2, "day": 1, "hour": 12, "gender": "男"}
selector = {"school": "classical", "policy": "classical_approx_v1", "version": "1"}
checks = 0
with tempfile.TemporaryDirectory(prefix="mingli-offline-") as folder:
    memory = Path(folder) / "memory.json"
    service.memory = UserMemory(memory)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    session = requests.Session()
    session.trust_env = False
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started, "API startup failed"

        def call(method, path, body=None, status=200):
            global checks
            r = session.request(method, f"http://127.0.0.1:{port}{path}", json=body, timeout=5)
            assert r.status_code == status, (method, path, r.status_code, r.text)
            checks += 1
            return r

        assert call("GET", "/api/health").json() == {"status": "ok", "provider": "sxtwl"}
        assert "/api/chart" in call("GET", "/").text
        chart = call("POST", "/api/chart", birth).json()
        assert chart["provider"] == "sxtwl" and len(chart["pillars"]) == 4
        facts = call("POST", "/api/analyze", {**birth, "question": "事业"}).json()
        assert facts["analysis"] is None and facts["metadata"]["facts"]
        analysis = call(
            "POST",
            "/api/analyze",
            {
                **birth,
                **selector,
                "question": " 事业 ",
                "target_date": "2025-02-10",
            },
        ).json()
        assert analysis["analysis"]["question"] == "事业"
        assert analysis["analysis"]["evidence"]["facts"] and "passed" in analysis["critique"]
        assert analysis["metadata"]["liu_month"]["heavenly_stem"] == "戊"
        assert analysis["metadata"]["liu_month"]["earthly_branch"] == "寅"
        ziwei = call("POST", "/api/ziwei", birth).json()
        assert ziwei
        windows = call(
            "POST",
            "/api/windows",
            {
                **birth,
                "target_year": 2024,
                "relation": "六合",
            },
        ).json()["windows"]
        assert [window["earthly_branch"] for window in windows] == ["辰", "未", "申", "子"]
        print(
            "Normal chart, facts, strategy analysis, 2025 month stem, Ziwei and overlapping window: PASS"
        )
        for year in (-(10**30), 0, 10000, 10**30):
            invalid = {**birth, "year": year}
            for method, path, extra in (
                ("POST", "/api/chart", {}),
                ("POST", "/api/analyze", {"question": "事业"}),
                ("POST", "/api/ziwei", {}),
                ("POST", "/api/windows", {"target_year": 2024}),
                ("PUT", "/api/memory/invalid", {}),
            ):
                call(method, path, {**invalid, **extra}, 422)
        print("Out-of-range birth years on all five endpoints: PASS")
        for question in ("", " ", "\t\n", "\u3000"):
            for selected in ({}, selector):
                call("POST", "/api/analyze", {**birth, **selected, "question": question}, 422)
            call("POST", "/api/memory/missing/analyze", {"question": question}, 422)
        call("PUT", "/api/memory/local-user", birth)
        before = memory.read_bytes()
        for question in ("", " ", "\t\n", "\u3000"):
            call("POST", "/api/memory/local-user/analyze", {"question": question}, 422)
            assert memory.read_bytes() == before
        recalled = call("GET", "/api/memory/local-user").json()
        assert recalled["history"] == []
        call("POST", "/api/memory/local-user/analyze", {"question": "事业"})
        recalled = call("GET", "/api/memory/local-user").json()
        assert [entry["question"] for entry in recalled["history"]] == ["事业"]
        print(
            "Blank questions rejected; invalid input leaves memory unchanged; valid memory flow: PASS"
        )
        exact = call("POST", "/api/western/chart", birth).json()["chart"]
        assert exact["sun"]["sign"] == "水瓶座" and exact["moon"]["sign"] == "白羊座"
        assert exact["provider"] == "astronomy-engine" and exact["time_precision"] == "minute"
        unknown = call(
            "POST", "/api/western/chart", {"year": 2024, "month": 3, "day": 20, "timezone": "UTC"}
        ).json()["chart"]
        assert unknown["instant_utc"] is None and unknown["sun"]["longitude_deg"] is None
        assert set(unknown["sun"]["possible_signs"]) == {"双鱼座", "白羊座"}
        moon = call(
            "POST", "/api/western/chart", {"year": 1990, "month": 2, "day": 1, "timezone": "UTC"}
        ).json()["chart"]["moon"]
        assert set(moon["possible_signs"]) == {"白羊座", "金牛座"}
        dst = {
            "year": 2024,
            "month": 11,
            "day": 3,
            "hour": 1,
            "minute": 30,
            "timezone": "America/New_York",
        }
        call("POST", "/api/western/chart", dst, 422)
        for fold, hour in ((0, "05"), (1, "06")):
            chart = call("POST", "/api/western/chart", {**dst, "fold": fold}).json()["chart"]
            assert chart["instant_utc"] == f"2024-11-03T{hour}:30:00+00:00"
        call("POST", "/api/western/chart", {**dst, "month": 3, "day": 10, "hour": 2}, 422)
        for invalid in (
            {"year": 1899},
            {"year": 2101},
            {"hour": True},
            {"minute": 10**30},
            {"timezone": "No/Such_Zone"},
        ):
            call("POST", "/api/western/chart", {**birth, **invalid}, 422)
        for invalid in ({"minute": 15}, {"fold": 0}):
            call(
                "POST", "/api/western/chart", {"year": 2024, "month": 3, "day": 20, **invalid}, 422
            )
        call("POST", "/api/windows", {**birth, "target_year": 10**30}, 422)
        for value in ("NaN", "Infinity", "-Infinity"):
            raw = '{"year":1990,"month":2,"day":1,"hour":12,"longitude":' + value + "}"
            r = session.post(
                f"http://127.0.0.1:{port}/api/western/chart",
                data=raw,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )
            assert r.status_code == 422
            checks += 1
        print(
            "Western exact/date-only signs, day/moon ingress, DST gap/folds, range/finite-number checks: PASS"
        )
        located = {**birth, "longitude": 121.4737, "latitude": 31.2304}
        full = call("POST", "/api/western/chart", located).json()["chart"]
        assert full["ascendant"]["sign"] == "金牛座"
        assert len(full["houses"]) == 12 and len(full["planets"]) == 8 and full["aspects"]
        equal = call("POST", "/api/western/chart", {**located, "house_system": "equal"}).json()[
            "chart"
        ]
        assert equal["houses"][0]["cusp_longitude_deg"] == equal["ascendant"]["longitude_deg"]
        partial = call("POST", "/api/western/chart", {**located, "hour": None}).json()["chart"]
        assert partial["ascendant"] is None and not partial["houses"] and not partial["aspects"]
        polar = call("POST", "/api/western/chart", {**located, "latitude": 90}).json()["chart"]
        assert polar["ascendant"] is None and polar["unavailable"] and len(polar["planets"]) == 8
        call("POST", "/api/western/chart", {**located, "house_system": "placidus"}, 422)
        synthesis = call("POST", "/api/synthesis", {**located, "question": "事业"}).json()
        assert synthesis["charts"]["bazi"]["day_master"] == "丁"
        assert synthesis["interpretation"]["focus"] == "行动与角色"
        missing = call("POST", "/api/synthesis", {**located, "hour": None}).json()
        assert missing["charts"]["bazi"] is missing["charts"]["ziwei"] is None
        call("POST", "/api/synthesis", {**located, "question": "  "}, 422)
        os.environ["MINGLI_API_KEY"] = "offline-test-key"
        call("POST", "/api/synthesis", located, 401)
        call("POST", "/api/western/chart", located, 401)
        assert call("GET", "/assets/app.css").content
        assert call("GET", "/assets/fonts/paper-serif.otf").content
        os.environ.pop("MINGLI_API_KEY", None)
        print(
            "Extended angles, houses, planets, aspects, synthesis, partial results and auth: PASS"
        )
        assert blocked == [], "App attempted an external connection"
        print(f"Offline API: {checks} HTTP checks passed; external connections/DNS: 0")
    finally:
        session.close()
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive(), "API did not shut down"
