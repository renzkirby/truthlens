import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useNavigate, useLocation } from "react-router-dom";

function LoginPage() {
   const { login } = useAuth();
   const navigate = useNavigate();
   const location = useLocation();
   const from = location.state?.from
      ? location.state.from.pathname + location.state.from.search
      : "/community";
   const [error, setError] = useState(null);
   const [formValues, setFormValues] = useState({
      username: "",
      password: "",
   });

   const handleInputChange = (event) => {
      const { name, value } = event.target;
      setFormValues({
         ...formValues,
         [name]: value,
      });
   };

   const handleSubmit = async () => {
      const response = await fetch("http://localhost:8000/api/auth/login/", {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ username: formValues.username, password: formValues.password }),
      });

      const data = await response.json();
      if (response.ok) {
         login(data.access, data.refresh);
         navigate(from, { replace: true });
      } else {
         setError(data.detail || "Something went wrong");
      }
   };

   return (
      <>
         <form
            onSubmit={(e) => {
               e.preventDefault();
               handleSubmit();
            }}>
            <label>Username:</label>
            <input
               type="text"
               name="username"
               value={formValues.username}
               onChange={handleInputChange}
               required
            />
            <br />
            <label>Password:</label>
            <input
               type="password"
               name="password"
               value={formValues.password}
               onChange={handleInputChange}
               required
            />
            <br />
            <input type="submit" />
         </form>
         {error && <p style={{ color: "red" }}>{error}</p>}
      </>
   );
}

export default LoginPage;
