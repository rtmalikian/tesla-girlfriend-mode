"""CLI: tgmode setup | auth | serve | preview | activate | suggestions | simulate"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import ConfigError, load_settings

__version__ = "0.1.0"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")


def _client(settings):
    from .tesla_client import TeslaClient
    return TeslaClient(settings.client_id, settings.client_secret,
                       region=settings.region, redirect_uri=settings.redirect_uri,
                       token_file=settings.token_file)


def _service(settings, with_client=False):
    from .service import GirlfriendModeService
    factory = (lambda: _client(settings)) if with_client else None
    return GirlfriendModeService(settings, client_factory=factory)


def cmd_auth(args, settings) -> int:
    client = _client(settings)
    print("Open this URL in your browser and authorize:")
    print(client.authorize_url())
    print("Virtual-key pairing: https://developer.tesla.com/docs/fleet-api#pairing")
    return 0


def cmd_setup(args, settings) -> int:
    from .setup import run_setup
    run_setup()
    return 0


def cmd_serve(args, settings) -> int:
    from .server import serve
    service = _service(settings, with_client=True)
    print("Vehicle and trip data go ONLY to your configured LLM backend "
          f"(TGM_AI_BASE_URL={settings.ai_base_url or 'none'}); learning "
          "stays on this computer.")
    serve(service)
    return 0


def _conditions(args) -> dict:
    return {
        "outside_temp_f": args.outside_temp,
        "speed_mph": args.speed,
        "parked": not args.driving,
        "returning_to_car": args.returning,
    }


def cmd_preview(args, settings) -> int:
    """Plain-English dry run: exactly what WOULD happen, before anything real."""
    service = _service(settings)
    outcome = service.activate(_conditions(args), execute=False)
    plan = outcome["plan"]
    print("PREVIEW — nothing has been changed on your car.")
    print("")
    print(plan["summary"])
    print("")
    print("What would happen, in order:")
    for r in outcome["results"]:
        tag = " (proposed API — simulated today)" if r["proposed"] else ""
        print(f"  • {r['description']}{tag}")
    print("")
    print("Happy with that? Run `tgmode activate` with the same options, "
          "or just say \"turn on girlfriend mode\" to the chat server.")
    return 0


def cmd_activate(args, settings) -> int:
    service = _service(settings, with_client=True)
    outcome = service.activate(_conditions(args), trigger="manual")
    print(service.activation_text(outcome))
    return 0


def cmd_suggestions(args, settings) -> int:
    service = _service(settings)
    cond = {"outside_temp_f": args.outside_temp}
    print(service.suggestions_text(**cond))
    return 0


def cmd_simulate(_args, settings) -> int:
    from .simulator import render_demo, run_demo
    print(render_demo(run_demo(settings)))
    return 0


def _add_condition_args(p):
    p.add_argument("--outside-temp", type=float, default=None,
                   help="Outside temperature in °F (omit if unknown)")
    p.add_argument("--speed", type=float, default=0,
                   help="Current speed in mph (default 0 = parked)")
    p.add_argument("--driving", action="store_true",
                   help="The car is driving, not parked")
    p.add_argument("--returning", action="store_true",
                   help="You're heading back to the parked car (pre-warm the seat)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tgmode",
        description="Girlfriend Mode — the passenger side, set up her way.")
    p.add_argument("--version", action="version", version=f"tgmode {__version__}")
    p.add_argument("--env-file", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Guided first-run setup (plain-language questions)")
    sub.add_parser("auth", help="Authorize with your Tesla account (one-time)")
    sub.add_parser("serve", help="Run the OpenAI-compatible API server")
    prev = sub.add_parser("preview", help="Plain-English dry run (changes nothing)")
    _add_condition_args(prev)
    act = sub.add_parser("activate", help="Turn Girlfriend Mode on for real")
    _add_condition_args(act)
    sug = sub.add_parser("suggestions",
                         help="What the app has learned from your trips together")
    sug.add_argument("--outside-temp", type=float, default=None,
                     help="Outside temperature in °F, for weather-fit suggestions")
    sub.add_parser("simulate", help="Demo with a pretend car and trips (no API calls)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
    else:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    try:
        settings = load_settings(dict(os.environ))
    except ConfigError as exc:
        print(f"Config problem: {exc}", file=sys.stderr)
        return 2
    handlers = {"setup": cmd_setup, "auth": cmd_auth, "serve": cmd_serve,
                "preview": cmd_preview, "activate": cmd_activate,
                "suggestions": cmd_suggestions, "simulate": cmd_simulate}
    try:
        return handlers[args.command](args, settings)
    except Exception as exc:  # human error messages, never a stack trace
        print(f"Something went wrong: {exc}. Check your settings with "
              "`tgmode setup`, then try again.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
