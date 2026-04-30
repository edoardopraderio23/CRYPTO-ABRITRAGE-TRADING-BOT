Project Omni-Arb: **Presentation Script**

Date: April 30, 2026
Team: Andrea Cammarano, Giacomo Lanni, Edoardo Praderio

Slide 1: THE VISION
"Good morning, together as a team, we are presenting Project Omni-Arb. In 2026, crypto markets have reached a level of efficiency where traditional spatial arbitrage is largely obsolete due to high-frequency competition. Our vision was to pivot to Triangular Arbitrage. We look for price imbalances between three currency pairs within a single exchange. This allows for near-instant execution and eliminates the risk of slow blockchain transfers. To achieve this, we’ve built a 'Human-AI' team. While Giacomo handled the quantitative modeling and Edoardo developed our machine learning filters, we integrated a GPT-4o Agent directly into our development workflow on GitHub to optimize our code for the low-latency requirements of 2026."

Slide 2: THE ARCHITECTURE 
"Thank you. To turn this vision into profit, we developed the Triple-Check System. First, we have 'The Scout.' This is our data layer. Using the CCXT library, we’ve built WebSocket streams that monitor order books in real-time across Binance, Kraken, and Coinbase. Second, is 'The Brain'—our core quant engine. We modeled the market as a directed graph. By transforming prices into negative logarithms, we turn the search for arbitrage into a 'Negative Cycle' detection problem, identifying profitable paths in under 10 milliseconds. Finally, we have 'The Guardian.' This is our Machine Learning model. It analyzes order book depth to predict 'Slippage.' It acts as a safety switch, only allowing the trade if it predicts an 85% or higher probability of success."

Slide 3: THE PROCESS
"Finally, let’s look at the workflow. Professor, we prioritized 'Process over Product.' Our entire development history is transparent on GitHub. We utilized an Agentic Framework defined in our AGENTS.md file. We assigned the AI specific tasks in our backlog, and you will see in our repository pull requests tagged as [AI-AGENT-CONTRIBUTION], which we then human-audited for financial safety. As of today, April 30th, we have successfully initialized our repository and workflow. Our roadmap is clear: By May 7th, we will have the Data and Quant engines integrated. Our final deliverable will be a robust, paper-traded solution, backed by an 8-page LaTeX report. In conclusion: Our edge lies in the intelligence to decide when NOT to trade. Thank you."

