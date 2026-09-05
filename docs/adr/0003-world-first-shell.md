# ADR 0003: World-first shell

- Status: Accepted
- Date: 2026-09-06

## Context

A sequence of setup, avatar, voice, agent, server, and Blender screens would turn OpenCraft into a dashboard and prevent beginners from reaching the world quickly.

## Decision

OpenCraft has exactly two primary screens: Lobby and World. Avatar, build, agent, chat, social, voice, map, invite, settings, and pause are temporary overlays over one of those primary screens.

A safe temporary avatar is generated automatically. Listening mode never enables microphone capture. Agent connection never enables agent listening. Sensitive states reset after reconnecting.

## Consequences

- New functionality must integrate as a contextual world action or overlay.
- Infrastructure terms remain hidden from ordinary participants.
- UX tests measure time from invite open to first world interaction and first safe AI preview.
- A feature needing a third primary screen requires a superseding ADR.
