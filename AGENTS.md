1. Project Context
This project is an automated Cryptocurrency Arbitrage Bot for the "Programming in Finance II" 2026 course. It uses graph theory to detect triangular arbitrage and Machine Learning to predict execution slippage.

2. Role of the AI Agent
The AI Agent acts as a Quant Developer. It is authorized to suggest code improvements, optimize mathematical algorithms, and generate unit tests.

3. Instructions for AI Contributions
AI agents (such as GitHub Copilot or LLMs) must follow these rules:

  A. Performance Standards
  Prioritize low latency in the src/engine/ folder.
  All algorithms must be optimized for speed to catch arbitrage gaps before they close.
  B. Security & Safety
  Never hardcode API keys.
  Ensure all trades are simulated in a "Paper Trading" mode unless explicitly toggled to live.
  C. Documentation Protocol
  Every Pull Request (PR) generated with AI assistance must include the tag: [AI-AGENT-CONTRIBUTION].
  The agent must provide a "Mathematical Rationale" explaining the logic behind any changes to the arbitrage detection engine.

4. Initial Task Backlog for AI
Task 1: Refactor the pathfinding logic to improve O-notation efficiency.
Task 2: Audit the exchange connectors for updated API endpoints.
Task 3: Create a test suite to verify "Log-Price" calculations for accuracy.

5. Human Oversight
The three human team members must review and approve all AI-suggested code via the GitHub Pull Request interface.
