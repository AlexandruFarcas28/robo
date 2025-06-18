import React, { useState, useRef, useEffect } from "react";
import "./App.css";

function App() {
  const [isAutonomous, setIsAutonomous] = useState(true);
  const [responses, setResponses] = useState([]);
  const [aiResponses, setAiResponses] = useState([]);
  const [aiPrompt, setAiPrompt] = useState("");
  const [tab, setTab] = useState("sam");
  const responsesEndRef = useRef(null);
  const aiEndRef = useRef(null);

  const ROBOT_URL = "http://192.168.xxx.xxx:5001/command";
  const CAMERA_URL = "http://192.168.xxx.xxx:5000/video_feed";
  const AI_URL = "http://192.168.xxx.xxx:5005/ai-command";

  // Dezactivăm scroll-ul automat
  // useEffect(() => {
  //   responsesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  // }, [responses]);
  // useEffect(() => {
  //   aiEndRef.current?.scrollIntoView({ behavior: "smooth" });
  // }, [aiResponses]);

  // Control cu Numpad când suntem în manual
  useEffect(() => {
    if (!isAutonomous) {
      const handleKeyDown = (e) => {
        if (e.code === "Numpad8") sendCommand("sus");
        if (e.code === "Numpad2") sendCommand("jos");
        if (e.code === "Numpad4") sendCommand("stanga");
        if (e.code === "Numpad6") sendCommand("dreapta");
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [isAutonomous]);

  const sendCommand = async (cmd) => {
    setResponses((r) => [...r, `Trimis: ${cmd}`]);
    if (cmd === "start") setIsAutonomous(true);
    if (cmd === "stop") setIsAutonomous(false);
    if (cmd === "mode:autonom") setIsAutonomous(true);
    if (cmd === "mode:manual") setIsAutonomous(false);

    try {
      const res = await fetch(ROBOT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      });
      const data = await res.json();
      setResponses((r) => [...r, `Robot: ${data.msg}`]);
    } catch (e) {
      setResponses((r) => [
        ...r,
        "Robot: Eroare la trimiterea comenzii sau robotul nu răspunde.",
      ]);
    }
  };

  const sendAiCommand = async (cmd) => {
    // 1. Arătăm comanda user
    setAiResponses((r) => [...r, `Tu: ${cmd}`]);
    try {
      // 2. Trimitem la AI
      const res = await fetch(AI_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      });
      const data = await res.json();

      // 3. Actualizăm UI cu răspunsul AI
      setAiResponses((r) => [...r, `Sam AI: ${data.msg}`]);

      // 4. PORNIM TTS doar cu TEXTUL răspunsului (fără prefix)
      await fetch(ROBOT_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: `say:${data.msg}` }),
      });
    } catch (e) {
      setAiResponses((r) => [
        ...r,
        "Sam AI: Eroare la trimiterea comenzii sau serverul AI nu răspunde.",
      ]);
    }
  };

  const handleAiSubmit = (e) => {
    e.preventDefault();
    if (aiPrompt.trim()) {
      sendAiCommand(aiPrompt.trim());
      setAiPrompt("");
    }
  };

  return (
    <div className="App">
      <h1>🤖 Control SAM & Sam AI</h1>
      <div style={{ display: "flex", gap: 18, marginBottom: 18 }}>
        <button
          onClick={() => setTab("sam")}
          style={{
            background: tab === "sam" ? "var(--accent)" : "var(--panel-bg)",
            color: "#fff",
            padding: "7px 25px",
            borderRadius: 8,
            border: "none",
            fontWeight: 600,
            fontSize: "1.08rem",
            marginRight: 10,
          }}
        >
          Control Robot
        </button>
        <button
          onClick={() => setTab("ai")}
          style={{
            background: tab === "ai" ? "var(--accent)" : "var(--panel-bg)",
            color: "#fff",
            padding: "7px 25px",
            borderRadius: 8,
            border: "none",
            fontWeight: 600,
            fontSize: "1.08rem",
          }}
        >
          Sam AI (Text)
        </button>
      </div>
      <div className="main-split">
        {/* CONTROALE + CHAT */}
        <div className="left-controls">
          {tab === "sam" ? (
            <>
              <div className="controls">
                <button onClick={() => sendCommand("start")}>Pornire</button>
                <button
                  className="destructive"
                  onClick={() => sendCommand("stop")}
                >
                  Oprire completă
                </button>
                <div className="checkbox-container">
                  <input
                    id="autonom"
                    type="checkbox"
                    checked={isAutonomous}
                    onChange={(e) => {
                      setIsAutonomous(e.target.checked);
                      sendCommand(
                        e.target.checked ? "mode:autonom" : "mode:manual"
                      );
                    }}
                  />
                  <label htmlFor="autonom">Autonom</label>
                </div>
              </div>

              {/* D-pad cruce */}
              {!isAutonomous && (
                <div className="manual-controls">
                  <div className="dpad-row">
                    <button onClick={() => sendCommand("sus")}>⬆️</button>
                  </div>
                  <div className="dpad-row">
                    <button onClick={() => sendCommand("stanga")}>⬅️</button>
                    <span className="dpad-center"></span>
                    <button onClick={() => sendCommand("dreapta")}>➡️</button>
                  </div>
                  <div className="dpad-row">
                    <button onClick={() => sendCommand("jos")}>⬇️</button>
                  </div>
                </div>
              )}

              <div className="responses">
                {responses.map((resp, idx) => (
                  <div key={idx}>{resp}</div>
                ))}
                <div ref={responsesEndRef}></div>
              </div>
            </>
          ) : (
            <>
              <form onSubmit={handleAiSubmit} className="prompt-form">
                <input
                  type="text"
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  placeholder="Întreabă-l pe Sam AI orice..."
                />
                <button type="submit">Trimite</button>
              </form>
              <div className="responses">
                {aiResponses.map((resp, idx) => (
                  <div key={idx}>{resp}</div>
                ))}
                <div ref={aiEndRef}></div>
              </div>
            </>
          )}
        </div>

        {/* CAMERA FEED */}
        <div className="camera-feed-right">
          <img
            src={CAMERA_URL}
            alt="Camera Feed"
            style={{
              width: "100%",
              maxWidth: 600,
              minWidth: 320,
              border: "2px solid #20304f",
              borderRadius: 18,
              background: "#0e1628",
              display: "block",
              boxShadow: "0 0 32px #161e2e",
            }}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
