# Content Intelligence Engine

## Goal
Build an autonomous system that observes generation behavior, learns from success/skip/duplicate patterns, improves dataset quality, controls AI cost, and safely adjusts generation inputs without manual admin approval.

## Core Flow
Observe → Score → Decide → Act → Learn

## Modules
- Analyzer
- Scorer
- Learner
- Planner
- Executor
- Budget Guard
- Reflection Engine

## Safety Rules
- Never spend AI budget without checking limits.
- Never disable items with low sample size.
- Never generate large batches automatically.
- Prefer weight adjustment before creating new data.
- Log every automatic decision.

## First Implementation
1. Track Topic/Audience/Goal performance.
2. Update performance after every success/skip.
3. Slowly adjust weights.
4. Add limited refill later.