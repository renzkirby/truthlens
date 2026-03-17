import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { useAuth } from "../context/AuthContext";
import NavigationBar from "../components/NavigationBar";

function ThreadDetailPage() {
   const [thread, setThread] = useState([]);
   const [loading, setLoading] = useState(true);
   const [error, setError] = useState(null);
   const { authFetch } = useAuth();
   const [searchParams] = useSearchParams();
   const threadId = searchParams.get("thread_id");
   const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

   useEffect(() => {
      const fetchThread = async () => {
         try {
            const threadData = await authFetch(`${API_BASE_URL}/threads/${threadId}/`, {
               method: "GET",
            });
            setThread(threadData);
         } catch (err) {
            setError("Failed to load thread");
         } finally {
            setLoading(false);
         }
      };
      fetchThread();
   }, []);

   return (
      <>
         <NavigationBar />
         {loading && <p>Thread loading...</p>}
         {error && <p>{error}</p>}
         {!loading && (
            <div>
               <p>{thread.caption}</p>
            </div>
         )}
      </>
   );
}

export default ThreadDetailPage;
