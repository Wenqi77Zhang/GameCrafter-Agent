# ADR-001: Start with a modular monolith

Status: accepted.

## Context

GameCrafter is developed by one person and needs a reliable local vertical slice before team, tenant, or scaling concerns are proven.

## Decision

Use one Python application with separate domain modules and adapter interfaces, plus one React frontend. Do not split ingestion, agent runtime, marketing, and persistence into network services.

## Consequences

- local setup, transactions, tests, and debugging remain manageable;
- domain boundaries still support a later service split;
- a split will require evidence such as independent scaling, security, ownership, or deployment needs;
- module boundaries require discipline because the process boundary does not enforce them.
