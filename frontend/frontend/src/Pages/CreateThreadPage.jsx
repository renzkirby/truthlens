import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate, useSearchParams } from "react-router-dom";

function CreateThreadPage() {
   const [loading, setLoading] = useState(true);
   const [submitting, setSubmitting] = useState(false);
   const [claim, setClaim] = useState(null);
   const [error, setError] = useState(null);
   const [searchParams] = useSearchParams();
   const claimId = searchParams.get("claim_id");
   const { authFetch } = useAuth();
   const navigate = useNavigate();
   const [formValues, setformValues] = useState({
      caption: "",
      source_url: "",
      flag_reason: "",
   });

   const handleInputChange = (e) => {
      const { name, value } = e.target;
      setformValues({
         ...formValues,
         [name]: value,
      });
   };

   const handleSubmit = async () => {
      setSubmitting(true);
      try {
         const responseData = await authFetch("http://localhost:8000/api/threads/", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
               claim_id: claimId,
               caption: formValues.caption,
               flag_reason: formValues.flag_reason,
            }),
         });
         navigate("/community");
      } catch (err) {
         setError("Something went wrong in creating a thread.");
      } finally {
         setSubmitting(false);
      }
   };

   useEffect(() => {
      if (!claimId) {
         setError("No claim ID provided");
         setLoading(false);
         return;
      }
      const fetchClaimData = async () => {
         try {
            const claimData = await authFetch(`http://localhost:8000/api/claims/${claimId}/`, {
               method: "GET",
            });
            setClaim(claimData);
            setformValues((prev) => ({
               ...prev,
               caption: claimData.ai_summary || "",
               source_url: claimData.source_link || "",
            }));
            console.log(claimData);
         } catch (err) {
            setError("Failed loading form");
         } finally {
            setLoading(false);
         }
      };
      fetchClaimData();
   }, []);

   return (
      <>
         {error && <p>{error}</p>}
         {loading && <p>Thread form loading...</p>}
         {!loading && claim && (
            <>
               <form
                  onSubmit={(e) => {
                     e.preventDefault();
                     handleSubmit();
                  }}>
                  <label>Claim Text/Caption</label>
                  <textarea
                     name="caption"
                     onChange={handleInputChange}
                     value={formValues.caption}
                  />
                  <br />
                  <label>Source URL</label>
                  <input
                     name="source_url"
                     type="url"
                     onChange={handleInputChange}
                     value={formValues.source_url}
                  />
                  <br />
                  <label>Why are you flagging this?</label>
                  <br />
                  <label htmlFor="fact">
                     <input
                        type="radio"
                        name="flag_reason"
                        id="fact"
                        value={"FACT"}
                        onChange={handleInputChange}
                     />
                     Fact
                  </label>
                  <br />
                  <label htmlFor="fake">
                     <input
                        type="radio"
                        name="flag_reason"
                        id="fake"
                        value={"FAKE"}
                        onChange={handleInputChange}
                     />
                     Fake
                  </label>
                  <br />
                  <label htmlFor="misleading">
                     <input
                        type="radio"
                        name="flag_reason"
                        id="misleading"
                        value={"MISLEADING"}
                        onChange={handleInputChange}
                     />
                     Misleading
                  </label>
                  <br />
                  <label htmlFor="satire">
                     <input
                        type="radio"
                        name="flag_reason"
                        id="satire"
                        value={"SATIRE"}
                        onChange={handleInputChange}
                     />
                     Satire
                  </label>
                  <br />
                  <label htmlFor="unverified">
                     <input
                        type="radio"
                        name="flag_reason"
                        id="unverified"
                        value={"UNVERIFIED"}
                        onChange={handleInputChange}
                     />
                     Unverified
                  </label>
                  <br />
                  <input type="submit" />
               </form>
               <p>------</p>
               <div>
                  <h3>AI PRE-ANALYSIS</h3>
                  <div>
                     <p>{claim.verdict}</p>
                     <p>{claim.consensus_score}</p>
                  </div>
               </div>
            </>
         )}
      </>
   );
}

export default CreateThreadPage;
