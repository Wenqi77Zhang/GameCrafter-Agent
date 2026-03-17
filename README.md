
# GameCrafter Agent: Autonomous Game Design LLM System

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Framework](https://img.shields.io/badge/framework-LangGraph%20%7C%20DSPy-orange)
![License](https://img.shields.io/badge/license-MIT-green)

> An enterprise-grade, autonomous AI Agent designed to streamline the game design process through dynamic Prompt Optimization, Retrieval-Augmented Generation (RAG), and Human-in-the-loop workflows.

## Overview

**GameCrafter Agent** is not just a standard chatbot. It is a multi-agent system that mimics the workflow of a professional game design team. By integrating top-tier system prompts (inspired by Devin & v0) and automated prompt engineering, it bridges the gap between a raw game idea and a comprehensive, balanced Game Design Document (GDD).

## System Architecture

The system is built on a sophisticated three-layer architecture, utilizing directed acyclic graphs (DAGs) to manage state transitions.

```mermaid
graph TD
    %% Define Node Styles
    classDef user fill:#f9f,stroke:#333,stroke-width:2px;
    classDef agent fill:#bbf,stroke:#333,stroke-width:2px;
    classDef data fill:#dfd,stroke:#333,stroke-width:2px;
    classDef decision fill:#ffd,stroke:#333,stroke-width:2px;

    %% Nodes
    A[User Idea/Input]
    B[Prompt Optimizer Node]
    C[RAG Researcher Node]
    D[Tavily Search / Vector DB]
    E[Planner & Executor Node]
    F[Draft Game Design Document]
    G{Human-in-the-Loop}
    H[Final Production GDD]

    %% Flow
    A --> B
    B -->|Optimized Expert Prompt| C
    C -->|Query Real-time Trends| D
    D -->|Return Contextual Data| C
    C -->|Contextualized Data| E
    E --> F
    F --> G
    G -->|Approve| H
    G -->|Reject & Provide Feedback| B

    %% Apply Styles (兼容所有老版本的写法)
    class A,H user;
    class B,C,E agent;
    class D,F data;
    class G decision;
    
