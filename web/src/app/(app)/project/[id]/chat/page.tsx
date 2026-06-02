import { notFound } from "next/navigation";
import { getProject, getChatMessages } from "@/lib/data/client";
import { ChatTab } from "@/components/features/chat/ChatTab";
import { ChatRealtime } from "@/components/features/realtime/ChatRealtime";

export default async function ChatPage(props: PageProps<"/project/[id]/chat">) {
  const { id } = await props.params;
  const [project, messages] = await Promise.all([getProject(id), getChatMessages(id)]);
  if (!project) notFound();
  return (
    <>
      <ChatRealtime projectId={id} />
      <ChatTab projectId={id} initialMessages={messages} />
    </>
  );
}
