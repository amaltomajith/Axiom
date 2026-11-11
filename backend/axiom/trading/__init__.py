"""Axiom Autopilot: an autonomous paper-trading agent behind a deterministic risk kernel.

    bars + news -> tournament -> brain.decide -> OrderIntent -> RiskKernel.review -> Broker -> journal

The brain (rules or an LLM) never chooses a quantity and never sees a broker. Every order passes the kernel.
"""
