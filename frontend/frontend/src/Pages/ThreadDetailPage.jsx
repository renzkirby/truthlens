import { useSearchParams } from "react-router";

function ThreadDetailPage() {
   const [searchParams] = useSearchParams();
   const threadId = searchParams.get("thread_id");
   return <>This is the detail page, {threadId}</>;
}

export default ThreadDetailPage;
