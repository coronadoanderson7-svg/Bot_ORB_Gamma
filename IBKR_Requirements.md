# Interactive Brokers (IBKR) Requirements

This document outlines the necessary account permissions, data subscriptions, and software required from Interactive Brokers to run this trading bot successfully.

---

### 1. IBKR Account

*   **Account Type:** You must have a funded brokerage account with Interactive Brokers. A paper trading account is highly recommended for development and testing, but live trading requires a funded live account.
*   **Trading Permissions:** Your account must have trading permissions enabled for the securities you intend to trade. Based on the project summary, you will need permissions for:
    *   **Options:** This is essential for trading the 0DTE (Zero Days to Expiration) contracts at the core of the strategy.
    *   Permissions are managed through the IBKR Account Management portal and may take a day or two to be approved.

---

### 2. Market Data Subscriptions

The bot requires specific real-time data feeds that are not included by default with a basic account. You must subscribe to the necessary data packages via IBKR Account Management. **Failure to subscribe will result in delayed, "frozen," or estimated data, causing the bot to fail.**

*   **Required for US Index Options (e.g., SPX, NDX):**
    *   **OPRA (Options Price Reporting Authority):** This is the primary subscription required for real-time US equity and index options data. It provides the quotes, trades, and option-specific data (Open Interest, Volume, Greeks like Gamma) needed for the GEX analysis.
    *   **Cboe Indexes:** Provides the real-time values for indices like the SPX, VIX, etc.

*   **General Guidance:**
    *   Always verify the required data packages for your specific instrument on the IBKR website.
        *   For non-professional users, these subscriptions are typically a few dollars per month and are billed to your account.
        *   You can use the "Market Data Assistant" in Account Management to help identify the subscriptions you need.

---

### 3. Required Software

The Python `ibapi` library does **not** connect directly to IBKR's servers. It connects to a client application running on your computer. You must have one of the following installed and running for the bot to work:

*   **Trader Workstation (TWS):** The full-featured trading platform. This is recommended for development and debugging, as you can visually monitor the data the bot is receiving, see the orders it places, and view logs.
*   **IB Gateway:** A lightweight, headless version of TWS. It consumes fewer system resources and is the preferred choice for running a tested, stable bot in a production or automated environment.

---

### 4. API Configuration

You must enable API access within TWS or IB Gateway after installing it:

1.  Open either TWS or IB Gateway.
2.  In the application's configuration settings, find the **API** section (In TWS: **File > Global Configuration > API > Settings**).
3.  Check the box to **"Enable ActiveX and Socket Clients"**.
4.  Note the **"Socket port"** number displayed. This port number must exactly match the `port` value in your `config.yaml` file.
    *   Default for TWS: `7497`
    *   Default for IB Gateway: `4002`
5.  **Trusted IP Addresses:** For security, it is best practice to add `127.0.0.1` to the list of "Trusted IP Addresses." This ensures that only applications running on the same machine as TWS/Gateway can connect to the API.
