// 형제 폴더(../client)를 로컬 패키지로 쓰기 위한 설정
const { getDefaultConfig } = require("expo/metro-config");
const path = require("path");

const config = getDefaultConfig(__dirname);
const client = path.resolve(__dirname, "../client");
config.watchFolders = [client];
config.resolver.nodeModulesPaths = [path.resolve(__dirname, "node_modules"), path.resolve(client, "node_modules")];
config.resolver.extraNodeModules = { "@photospot/client": client };
module.exports = config;
