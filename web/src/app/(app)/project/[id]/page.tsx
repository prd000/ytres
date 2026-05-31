import { redirect } from "next/navigation";

export default async function ProjectIndexPage(props: PageProps<"/project/[id]">) {
  const { id } = await props.params;
  redirect(`/project/${id}/plan`);
}
