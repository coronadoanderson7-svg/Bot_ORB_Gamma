Inquiry #T822564 - U24180016
Summary: Inquiry Regarding Missing Put Option Open Interest Data (Tick Type 28) in Paper Trading Account
andersonjordan 2026/02/12 12:58:49
Subject: Inquiry Regarding Missing Put Option Open Interest Data (Tick Type 28) in Paper Trading Account
Body:
Dear Interactive Brokers Support Team,
I am writing to you today regarding a data discrepancy I am experiencing with my paper.
I am developing an application using the TWS API (Python) that requires real-time option chain data for SPX, specifically the open interest (OI) for both call and put options.
My application is successfully receiving Call Open Interest (Tick Type 27) for SPX options. However, for the corresponding put options in the same request batches, I am consistently not receiving any Put Open Interest (Tick Type 28) data. I am receiving other data points like gamma for both calls and puts correctly.
For your technical reference, here is how my application is requesting and processing the data:
1. Data Request: For each option contract (both calls and puts), I am making a market data request using the reqMktData function with the generic tick list "101,104". This is intended to subscribe to both "Option Volume, Open Interest" and "Option Greeks" data streams.
2. Data Processing: My application's EWrapper implementation listens for the tickSize callback. The data is placed into a queue, which my application then consumes. The logic specifically checks for tickType 27 (Call OI) and 28 (Put OI) to populate the open interest values, as shown in this snippet from my ib_provider.py file:
python
# From strategy/gex/ib_provider.py
def _collect_market_data(self, ib_connector: "IBConnector", req_id_map: Dict, data_aggregator: Dict):
# ...
try:
# Check for open interest from the queue (non-blocking)
oi_req_id, tick_type, size = ib_connector.wrapper.tick_size _queue.get_nowait()
if oi_req_id in data_aggregator and data_aggregator[oi_req_id]["oi"] is None:
if tick_type in [27, 28]: # Call OI, Put OI
data_aggregator[oi_req_id]["oi"] = size
except Empty:
pass # Queue is empty, continue
# ...
The fact that I receive Tick Type 27 but not Tick Type 28 for the same underlying and expiration is causing a significant data bias for my application.
Example:
INFO:strategy.gex.ib_provider: Strike | Call OI | Call Gamma | Put OI | Put Gamma
INFO:strategy.gex.ib_provider:---------- | ---------- | ------------ | ---------- | ------------
INFO:strategy.gex.ib_provider: 6855.00 | 62 | 0.0058 | 0 | 0.0058
INFO:strategy.gex.ib_provider: 6860.00 | 84 | 0.0068 | 0 | 0.0063
INFO:strategy.gex.ib_provider: 6865.00 | 83 | 0.0068 | 0 | 0.0068
INFO:strategy.gex.ib_provider: 6870.00 | 51 | 0.0072 | N/A | N/A
INFO:strategy.gex.ib_provider: 6880.00 | 88 | 0.0080 | 0 | 0.0080
INFO:strategy.gex.ib_provider: 6885.00 | 132 | 0.0084 | 0 | 0.0085
INFO:strategy.gex.ib_provider: 6890.00 | 149 | 0.0086 | 0 | 0.0086
INFO:strategy.gex.ib_provider: 6895.00 | 78 | 0.0087 | 0 | 0.0087
INFO:strategy.gex.ib_provider: 6900.00 | 871 | 0.0088 | 0 | 0.0088

My primary question is whether this is expected behavior or a limitation of the paper trading environment. It is crucial for me to know if this issue will also be present in a live, funded account.
Could you please investigate and clarify:
1. Is there a known reason why the API would provide Call Open Interest (Tick Type 27) but not Put Open Interest (Tick Type 28) when requested in the same manner?
2. Is this behavior specific to paper trading accounts, or would I experience the same issue in a live account?
Having symmetrical and complete data for both calls and puts is essential for my application to function correctly. Any insight you can provide would be greatly appreciated.

Versions:
TWS API
Name: ibapi
Version: 9.81.1.post1
Summary: Official Interactive Brokers API
Home-page: LINK../tws-api Author: IBG LLC
Author-email: dnastase@interactivebrokers.com License: IB API Non-Commercial License or the IB API Commercial License
TWS/IB: version 10.42
Operating system: Windows
Thank you for your time and assistance.
Sincerely,
Jordan Call
IBCS 2026/02/12 13:44:02
Gentile Sig. Call,

Thank you for contacting Interactive Brokers.

Would it be possible for you to generate and submit logs that record this error?

The general process would look like: (1) enable all logging capabilities in TWS, (2) recreate the request that yielded this error, (3) submit logs and rough timestamp, and (4) optionally, dial back the logging so you aren't generating huge log files.

To turn on the maximum level of logging:
1) In TWS, go to the File menu at the top left and open Global Configuration
2) Head to API >> Settings
3) Check the box for "Create API message log file"
4) Check the box for "Include market data in API log file"
5) Set the "Logging Level" dropdown to "Detail"
6) Click "Apply" then "OK" on the bottom to save these settings.

At this point, you can submit a request to the API, and any erroneous behavior will be captured.

To submit logs:
1) In TWS or IB Gateway, press Ctrl+Alt+H (CMD+OPT+H) to bring up the Upload Diagnostics window
2) In the "reason" text field, you can put "Attention: Allison" (so I can find the logs faster)
3) Find the tiny down arrow in the upper right corner, click it and select "Advanced View"
4) Make sure "Full internal state of the application" is checked
5) Make sure "Include previous days logs and settings" is unchecked.
5) Click Submit
6) Notify me through this ticket as soon as you have submitted your request.


Cordiali saluti,
Allison P

Servizio Clienti di IBKR
andersonjordan 2026/02/12 14:23:37
Hello Allison,

Thanks for your help, i have followed all the instructions, just want to notify that i have submitted the API request.

Thank you for your time and assistance.
Sincerely,
Jordan Call
IBCS 2026/02/12 14:36:24
Gentile Sig. Call,

Thank you for uploading the diagnostics bundle.

After reviewing the logs, the likely cause of this issue you're experiencing is your deprecated API package. Your client-side application is using an API package which is no longer supported and no longer functional. Please see below, retrieved from the diagnostics bundle:

2026-02-12 11:05:37.952 [TE] INFO [JTS-EServerSocket-1971] - [-:157:157:1:0:0:0:SYS] Server version is 157

It's recommended to completely uninstall the old API package from your machine. If you downloaded this package by running the command "pip install ibapi", please run the command "pip uninstall ibapi" in your terminal.

Next, please download either the Latest or Stable TWS API version, found here on our GitHub: LINK../interactivebrokers.github.io

You can also review our TWS API documentation to read through installation steps and recommendations: LINK../#windows-install

Finally, please ensure you update the Python interpreter so that the TWS API modules can be imported and utilized: LINK../#setup-python

Please let me know if this was able to resolve the issue for you and if you have any further questions or concerns.


Cordiali saluti,
Allison P

Servizio Clienti di IBKR
andersonjordan 2026/02/13 13:21:57
Dear Allison,

Thank you for your previous analysis and guidance.

Following your instructions, I have completely uninstalled the old, deprecated ibapi package (version 9.81.1.post1) and have installed the latest stable version from your official GitHub repository. My environment is now running ibapi version 10.43.2 on Windows, connecting to the latest IB Gateway.

Unfortunately, despite updating the API client, the original problem persists. My application's calculations remain biased due to incomplete data, which is critically affecting its performance.

Here is a detailed summary of the issue and our implementation:

1. The Core Problem: Missing Put Open Interest (TickType 28)

The primary issue is that while we successfully receive Call Open Interest (TickType 27), the API consistently returns 0 or no data at all for Put Open Interest (TickType 28) for the same SPX strikes.

This is evident in our application's output from the latest run, where the Put OI column is almost entirely 0 or N/A, while the Call OI is populated correctly. This occurs for active, near-the-money strikes where there is significant open interest.

Example from our log at 09:25:22:

plaintext
Show full code block
Strike | Call OI | Call Gamma | Put OI | Put Gamma
---------|------------|--------------|------------|--------------
6825.00 | 672 | 0.0043 | 0 | 0.0043
6830.00 | 700 | 0.0049 | 0 | 0.0049
...
6850.00 | 3401 | 0.0080 | N/A | N/A
...
6875.00 | 1124 | 0.0116 | 0 | 0.0116
2. Our Implementation for Requesting Data

To provide full clarity, here is the exact methodology our Python application uses to request this data:

First, we build a list of ibapi.contract.Contract objects for both Calls and Puts for the desired strikes.

Second, for each contract in the list, we request streaming data using reqMktData with the generic tick list "101,104" to get Open Interest and Greeks. The call within our code is as follows:

python
# From strategy/gex/ib_provider.py
# For each contract object...
ib_connector.req_market_data(req_id, contract, "101,104", False, False)
Finally, we process the data from the tickSize EWrapper event, which is placed into a queue. Our logic specifically checks for TickType 27 (Call OI) and TickType 28 (Put OI) to retrieve the open interest values:

python
Show full code block
# From strategy/gex/ib_provider.py
# Loop to process data from the queue...
try:
oi_req_id, tick_type, size = ib_connector.wrapper.tick_size _queue.get_nowait()
if oi_req_id in data_aggregator:
# We are correctly receiving tick_type 27, but not 28.
if tick_type in [27, 28]: # Call OI, Put OI
data_aggregator[oi_req_id]["oi"] = size
except Empty:
pass # Queue is empty
3. Related Symptoms: Timeouts and "Competing Session" Errors

When we run the code above for a batch of ~40 contracts (20 strikes, calls and puts), we experience significant timeouts. Many requests in the batch fail to return complete data (gamma and OI) within a 5-second timeout window, as shown in this log warning:

2026-02-13 09:25:15.583 | WARNING | Batch data collection timed out after 5s. 6/20 requests did not complete. GEX data will be partial.

Furthermore, after these initial batch requests are cancelled, subsequent data requests begin to fail with the following error, which eventually halts our application:

2026-02-13 09:37:41.970 | ERROR | IB Error: ReqId: 2303, Code: 10197, Msg: No market data during competing live session

Our Questions:

Given our implementation, is the missing Put OI (TickType 28) a known limitation of the paper trading environment, or is there a flaw in our request method?
What is the best practice for reliably streaming both OI and Greeks for a list of ~40 option contracts? Does making batch calls to reqMktData with "101,104" in a loop lead to the timeouts and "competing session" errors we are observing?
Could you advise on a more robust solution or provide a code example to ensure we receive complete and accurate data for our calculations without causing these data stream conflicts?
I am ready to provide a new diagnostics bundle if needed. Any insight you can offer would be immensely helpful.

Thank you for your continued support.

Sincerely,

Jordan Call
IBCS 2026/02/17 10:14:32
Gentile Sig. Call,

Thank you for your reply.

In order to further troubleshoot, I'll need to analyze the exact requests and responses between your clientside application and the TWS.

Would you be able to upload another set of diagnostics logs again for me to review?

Please let me know via this web ticket once you've submitted the logs.


Cordiali saluti,
Allison P

Servizio Clienti di IBKR
andersonjordan 2026/02/17 13:58:02
"Dear Allison,

Thank you for your continued assistance. As requested, I have submitted the logs for your review. We are still experiencing an issue where the Open Interest for all put options is displaying as 0.

Please let me know if you can identify the cause of this discrepancy or if there is a more effective way to structure our data requests."

Best Regards

Jordan Call
andersonjordan 2026/02/17 14:13:00
"Hi again, Allison,

One more detail: please review the log from 2026-02-17 09:33:50.012. I ran the script at that time and successfully replicated the error, so you should see it clearly there."

Thanks

Jordan Call
IBCS 2026/02/17 14:14:30
Gentile Sig. Call,

Thank you for uploading the logs for us to review.

As a part of the investigation process, could you please let me know which function call you're making when you fail to receive Open Interest for put options? For example, reqMktData(), reqHistoricalData(), reqRealTimeBars(), etc.

Cordiali saluti,
Allison P

Servizio Clienti di IBKR
andersonjordan 2026/02/17 14:18:21
Hi again, Allison,

Follow up:

One more detail: please review the log from 22026-02-17 12:33:37.881. I ran the script at that time and successfully replicated the error, so you should see it clearly there."

Thanks

Jordan Call
IBCS 2026/02/17 15:09:14
Gentile Sig. Call,

Regrettably, I cannot reproduce this error in my test environment as this options contract you were submitting requests for has expired today.

In addition, I cannot reproduce this error for other SPX options contracts that are expiring further out in the future.

Can you please delete all current IB Gateway and API logs on your computer, then re-generate this error with options contracts that are expiring in the next several days?

To delete IB Gateway and API logs from your computer, please see these steps here: LINK../#log-location
Cordiali saluti,
Allison P

Servizio Clienti di IBKR
andersonjordan 2026/02/17 17:15:17
Dear Allison P,

Thanks so much for your help, as all the contacts that i am using are 0dte, and the program only works during merket hours i am not able to replicate the error today. i will follow the instructions to delete all the logs, and tomorrow as soon as the market opens i will replicate the error. thanks again for your help.

also i am goint to add my code 1. how we build the contract and then the request for the market data.

Building contract.

def _build_option_contracts(self, ticker: str, expiration: str, strikes: List[float]) -> List[Contract]:
"""Builds a list of call and put Contract objects."""
logger.info(f"Building {len(strikes) * 2} option contract objects...")
contracts = []
for strike in strikes:
for right in ["C", "P"]:
contract = Contract()
contract.symbol = ticker
contract.secType = "OPT"
contract.exchange = self.config.instrument.exchang e
contract.currency = self.config.instrument.currenc y
contract.lastTradeDateOrContra ctMonth = expiration
contract.strike = strike
contract.right = right
contract.multiplier = str(self.config.gex.option_multipl ier)
contracts.append(contract)
return contracts

Request information:

def _request_market_data(self, ib_connector: "IBConnector", contracts: List[Contract]) -> Tuple[Dict, Dict]:
"""Requests streaming market data for a list of contracts."""
req_id_map = {}
data_aggregator = {}

logger.info(f"Requesting streaming market data for {len(contracts)} option contracts.")
for contract in contracts:
req_id = ib_connector.get_next_request_ id()
req_id_map[req_id] = {
"strike": contract.strike,
"right": contract.right,
"contract": contract, # store for put OI fallback
}
data_aggregator[req_id] = {"gamma": None, "oi": None}
# Request greeks (104) and open interest (101) via a streaming request
ib_connector.req_market_data(req_id, contract, "101,104", False, False)

return req_id_map, data_aggregator

Being this the "ib_connector.req_market_data(req_id, contract, "101,104", False, False)" the code used for getting the streamed real time - data.

Jordan Call
andersonjordan 2026/02/18 10:32:25
Dear Allison P,

As you suggested yesterday i have deleted all the logs and i have replicated the escenario this morning, ill add a brief description of the problem and the code used for the request.

Data Request: For each option contract (both calls and puts), my application makes a market data request using the req_market_data function with the generic tick list "101,104". This is intended to subscribe to both "Option Volume, Open Interest" and "Option Greeks" data streams. The code for this request is as follows:

python
# From strategy/gex/ib_provider.py
ib_connector.req_market_data(req_id, contract, "101,104", False, False)

Data Processing: My application's EWrapper implementation listens for the tickSize callback and processes the data from a queue. The logic specifically checks for tickType 27 (Call OI) and 28 (Put OI) to populate the open interest values.

My Questions

Could you please investigate and clarify the following:

Is it expected behavior for a live data request (market data type 1) to return 0 for Put Open Interest (Tick Type 28) during the trading session, while Call Open Interest (Tick Type 27) is delivered correctly?

Is this behavior specific to the paper trading environment, or will I experience the same issue in a live, funded account?

Thanks again for your help

Jordan Call
IBCS 2026/02/18 11:25:02
Gentile Sig. Call,

Taking a look at the logs you have uploaded, I can see that the API is delivering you Put Open Interest (Tick Type 28) when you request it in your clientside application.

Please see a few examples from the logs here:

1) <- [1;reqId: 1935 contract { conId: 0 symbol: "SPX" secType: "OPT" lastTradeDateOrContractMonth: "20260218" strike: 6825.0 right: "P" multiplier: 100.0 exchange: "CBOE" currency: "USD" } genericTickList: "101,104"]
-> [2;reqId: 1935 tickType: 28 size: "1736"]

2) <- [1;reqId: 1929 contract { conId: 0 symbol: "SPX" secType: "OPT" lastTradeDateOrContractMonth: "20260218" strike: 6810.0 right: "P" multiplier: 100.0 exchange: "CBOE" currency: "USD" } genericTickList: "101,104"]
-> [2;reqId: 1929 tickType: 28 size: "906"]

3) <- [1;reqId: 1945 contract { conId: 0 symbol: "SPX" secType: "OPT" lastTradeDateOrContractMonth: "20260218" strike: 6850.0 right: "P" multiplier: 100.0 exchange: "CBOE" currency: "USD" } genericTickList: "101,104"]
-> [2;reqId: 1945 tickType: 28 size: "1817"]

In each instance where you specify " right: "P" " in your request, you receive the data. However, if you specify " right: "C" " in your request, then Tick Type 27 is delivered and Tick Type 28 is left as a 0. This applies in the vice/versa scenario as well.

Please let me know if you have any additional questions or concerns.


Cordiali saluti,
Allison P

Servizio Clienti di IBKR