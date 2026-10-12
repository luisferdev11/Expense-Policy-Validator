import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { ActorProvider, ToastProvider } from "./lib/hooks";
import { ReceiptsProvider } from "./lib/receipts";
import "./styles/tokens.css";
import "./styles/ledgerline.css";
import "./styles/app.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ActorProvider>
        <ToastProvider>
          <ReceiptsProvider>
            <App />
          </ReceiptsProvider>
        </ToastProvider>
      </ActorProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
