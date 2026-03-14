import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

function RegisterPage() {
   const { login } = useAuth();
   const navigate = useNavigate();
   const [error, setError] = useState(null);
   const [formValues, setFormValues] = useState({
      username: "",
      email: "",
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
      const response = await fetch("http://localhost:8000/api/auth/register/", {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({
            username: formValues.username,
            email: formValues.email,
            password: formValues.password,
         }),
      });

      const data = await response.json();
      if (response.ok) {
         login(data.access, data.refresh);
         navigate("/community");
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
            <label>Email Address:</label>
            <input
               type="email"
               name="email"
               value={formValues.email}
               onChange={handleInputChange}
               required
            />
            <label>Password:</label>
            <input
               type="password"
               name="password"
               value={formValues.password}
               onChange={handleInputChange}
               required
            />
            <input type="submit" />
         </form>
         {error && <p style={{ color: "red" }}>{error}</p>}
      </>
   );
}

export default RegisterPage;
