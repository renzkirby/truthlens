import Icons from "../Icons.jsx";

import "./InvestigationContextLinks.css";

function formatThreadStatus(value) {
   if (!value) {
      return "Unknown";
   }

   return String(value)
      .replaceAll("_", " ")
      .toLowerCase()
      .replace(/\b\w/g, (character) => character.toUpperCase());
}

function sortThreads(threads) {
   return [...threads].sort((left, right) => {
      const leftDate = new Date(left?.created_at ?? 0).getTime();

      const rightDate = new Date(right?.created_at ?? 0).getTime();

      return rightDate - leftDate;
   });
}

function InvestigationContextLinks({ claim }) {
   const claimId = claim?.id;

   const threads = sortThreads(Array.isArray(claim?.community_threads) ? claim.community_threads : []);

   return (
      <div className="investigation-context-links">
         {claimId && (
            <a
               className="investigation-context-link"
               href={`/analysis/${claimId}`}
               target="_blank"
               rel="noopener noreferrer"
            >
               <Icons name="brain-circuit" size={14} />
               View AI analysis
               <Icons name="external-link" size={12} />
            </a>
         )}

         {threads.length === 1 ? (
            <a
               className="investigation-context-link"
               href={`/thread/detail/${threads[0].id}`}
               target="_blank"
               rel="noopener noreferrer"
            >
               <Icons name="message-square" size={14} />
               View community discussion
               <Icons name="external-link" size={12} />
            </a>
         ) : threads.length > 1 ? (
            <details className="investigation-discussions">
               <summary>
                  <Icons name="message-square" size={14} />
                  Community discussions ({threads.length})
                  <Icons name="chevron-down" size={13} />
               </summary>

               <div className="investigation-thread-list">
                  {threads.map((thread, index) => (
                     <a key={thread.id} href={`/thread/detail/${thread.id}`} target="_blank" rel="noopener noreferrer">
                        <span className="investigation-thread-caption">
                           {thread.caption || `Discussion ${index + 1}`}
                        </span>

                        <span className="investigation-thread-status">{formatThreadStatus(thread.status)}</span>

                        <Icons name="external-link" size={12} />
                     </a>
                  ))}
               </div>
            </details>
         ) : (
            <span className="investigation-context-muted">
               <Icons name="message-square" size={14} />
               No community discussion
            </span>
         )}
      </div>
   );
}

export default InvestigationContextLinks;
