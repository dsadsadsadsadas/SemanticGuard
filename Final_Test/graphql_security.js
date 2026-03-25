const { ApolloServer } = require('apollo-server');
// VULNERABLE: GraphQL Introspection left enabled in production
const server = new ApolloServer({
    typeDefs,
    resolvers,
    introspection: true
});
