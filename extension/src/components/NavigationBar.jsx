import "./NavigationBar.css";
import { ArrowRight, Link, FileText, Sparkles } from "lucide-react";

const tools = [
   { id: "url-upload", label: "Analyze URL", icon: Link },
   { id: "file-upload", label: "Upload File", icon: FileText },
   { id: "detect-deepfake", label: "Deepfake Detection", icon: Sparkles },
];

export default function NavigationBar({ setActiveLink }) {
   return (
      <nav className="extension-tools" aria-label="Verification tools">
         {tools.map(({ id, label, icon }) => {
            const Icon = icon;

            return (
               <button type="button" className="extension-tool" key={id} onClick={() => setActiveLink(id)}>
                  <Icon size={17} aria-hidden="true" />
                  <span>{label}</span>
                  <ArrowRight size={15} className="tool-arrow" aria-hidden="true" />
               </button>
            );
         })}
      </nav>
   );
}
