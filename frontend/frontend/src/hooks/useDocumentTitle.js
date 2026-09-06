import { useEffect } from "react";

export function useDocumentTitle(title) {
   useEffect(() => {
      const previousTitle = document.title;
      document.title = title;

      return () => {
         if (document.title === title) {
            document.title = previousTitle;
         }
      };
   }, [title]);
}
