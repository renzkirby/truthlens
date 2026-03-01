import "./SnippingTool.css";

function SnippingTool({ handleSnipClick, isSnipping }) {
   return (
      <div className="snipping-page">
         <div className="gray-placeholder"></div>
         <button
            className="snip-btn"
            onClick={handleSnipClick}
            disabled={isSnipping}
            style={{ padding: "10px 20px", cursor: "pointer", marginTop: "10px" }}>
            {isSnipping ? "Snipping..." : "Verify"}
            <span className="icon">🔍</span>
         </button>
      </div>
   );
}

export default SnippingTool;
