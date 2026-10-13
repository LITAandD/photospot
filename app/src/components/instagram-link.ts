/** 웹·앱 공용: 공개 Instagram 게시물(p/reel) 원본 주소만 연다. */
export type InstagramPost = { permalink: string; label: string; checked_at: string };
const PERMALINK = /^https:\/\/www\.instagram\.com\/(p|reel)\/[A-Za-z0-9_-]{5,64}\/$/;
export const isInstagramPermalink = (url: unknown): url is string => typeof url === "string" && PERMALINK.test(url);
export const safeInstagramPosts = (posts: InstagramPost[]) => posts.filter((p) => isInstagramPermalink(p.permalink));
